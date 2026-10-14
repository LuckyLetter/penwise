--- === Penwise ===
---
--- Select text in any app, press a hotkey, and review suggested English fixes,
--- each with a short note. Press Return to replace your selection.
---
--- Requires the `penwise` command: https://github.com/LuckyLetter/penwise

local obj = {}
obj.__index = obj

obj.name = "Penwise"
obj.version = "0.6.18"
obj.author = "LuckyLetter"
obj.homepage = "https://github.com/LuckyLetter/penwise"
obj.license = "Apache-2.0 - https://opensource.org/licenses/Apache-2.0"

--- Penwise.bin
--- Variable
--- Path to the `penwise` executable. `penwise setup-mac` sets this for you.
obj.bin = os.getenv("HOME") .. "/.local/bin/penwise"

--- Penwise.args
--- Variable
--- Arguments placed before the subcommand, e.g. `{ "-m", "penwise" }` when `bin` is a Python interpreter.
obj.args = {}

--- Penwise.wholeFieldLimit
--- Variable
--- With nothing selected, a text field holding at most this many characters (a message,
--- a comment, a form field) is checked as a whole; in a longer one, the paragraph at the
--- cursor is. Set to 0 to always require a selection.
obj.wholeFieldLimit = 2000

--- Penwise.showMenu
--- Variable
--- Show the Penwise icon in the menu bar (when `start()` is called).
obj.showMenu = true

--- Penwise.checkForUpdates
--- Variable
--- Look for a new version once a day; when there is one, the menu offers to update.
obj.checkForUpdates = true

--- Penwise.background
--- Variable
--- Keep Hammerspoon out of sight: no menu bar or Dock icon of its own, only Penwise's ✎. Set by
--- the Penwise installer, for people who have Hammerspoon only for Penwise.
obj.background = false

--- Penwise.logFile
--- Variable
--- A log of what the hotkey did, step by step (never your text), which `penwise doctor` shows
--- when something doesn't work. Set to nil to keep no log.
obj.logFile = os.getenv("HOME") .. "/Library/Logs/penwise-hotkey.log"

obj.logger = hs.logger.new("Penwise")

local PANEL_WIDTH = 640
local HAMMERSPOON = "org.hammerspoon.Hammerspoon"

-- Terminals show past commands and output as one big text area, and a paste there types at the
-- prompt instead of replacing anything. So only a selection is checked, and Replace clears the
-- line you're typing (⌃E ⌃U, which shells and Claude Code understand) before pasting the fix.
-- Chromium browsers build their accessibility tree for other apps only when asked to.
local CHROMIUM_BROWSERS = {
  ["com.google.Chrome"] = true,
  ["com.google.Chrome.canary"] = true,
  ["com.microsoft.edgemac"] = true,
  ["com.brave.Browser"] = true,
  ["company.thebrowser.Browser"] = true,
  ["com.vivaldi.Vivaldi"] = true,
  ["com.operasoftware.Opera"] = true,
  ["org.chromium.Chromium"] = true,
}

local TERMINALS = {
  ["com.apple.Terminal"] = true,
  ["com.googlecode.iterm2"] = true,
  ["dev.warp.Warp-Stable"] = true,
  ["net.kovidgoyal.kitty"] = true,
  ["org.alacritty"] = true,
  ["io.alacritty"] = true,
  ["com.mitchellh.ghostty"] = true,
  ["com.github.wez.wezterm"] = true,
  ["co.zeit.hyper"] = true,
}

local spoonPath = hs.spoons.scriptPath()

local function readFile(path)
  local file = assert(io.open(path, "r"))
  local content = file:read("*a")
  file:close()
  return content
end

local function concat(first, second)
  local out = {}
  for _, value in ipairs(first) do table.insert(out, value) end
  for _, value in ipairs(second) do table.insert(out, value) end
  return out
end

-- Where Hammerspoon keeps the hotkeys' letter chosen in the settings.
local LETTER_SETTING = "penwise.hotkeyLetter"

local function restoreClipboard(saved)
  if saved and next(saved) then
    hs.pasteboard.writeAllData(saved)
  else
    hs.pasteboard.clearContents()
  end
end

-- Split complete lines off the front of `buffer`; returns the lines and the rest.
local function takeLines(buffer)
  local lines = {}
  while true do
    local newline = buffer:find("\n", 1, true)
    if not newline then break end
    table.insert(lines, buffer:sub(1, newline - 1))
    buffer = buffer:sub(newline + 1)
  end
  return lines, buffer
end

function obj:_log(format, ...)
  if not self.logFile then return end
  local line = os.date("%Y-%m-%d %H:%M:%S  ") .. string.format(format, ...) .. "\n"
  pcall(function()
    local size = hs.fs.attributes(self.logFile, "size")
    if type(size) == "number" and size > 200000 then os.rename(self.logFile, self.logFile .. ".old") end
    local file = io.open(self.logFile, "a")
    if file then
      file:write(line)
      file:close()
    end
  end)
end

-- "3 fixes: Articles, Word form"
local function summarize(changes)
  local labels, seen = {}, {}
  for _, change in ipairs(changes) do
    if change.label and not seen[change.label] and #labels < 3 then
      seen[change.label] = true
      table.insert(labels, change.label)
    end
  end
  local count = #changes == 1 and "1 fix" or (#changes .. " fixes")
  return #labels > 0 and (count .. ": " .. table.concat(labels, ", ")) or count
end

function obj:init()
  self.html = readFile(spoonPath .. "panel.html")
  self.panelHeight = 240 -- until the panel says how much room its content needs
  self.run = 0
  self.queue = {}
  return self
end

--- Penwise:bindHotkeys(mapping)
--- Method
--- Binds hotkeys. Keys of `mapping`:
---  * `fix`: review fixes for the selected text
---  * `improve`: also improve clarity and flow
---  * `quick`: fix the selected text and replace it right away, without the review panel
---
--- The letter chosen in the settings (E for ⌃⌥E, ⌃⌥⇧E and ⌃⌥⌘E) replaces the one in `mapping`.
function obj:bindHotkeys(mapping)
  self.hotkeySpec = mapping
  local letter = hs.settings.get(LETTER_SETTING)
  if letter then
    local chosen = {}
    for name, spec in pairs(mapping) do chosen[name] = { spec[1], letter } end
    mapping = chosen
  end
  hs.spoons.bindHotkeysToSpec({
    fix = function() self:check("fix") end,
    improve = function() self:check("improve") end,
    quick = function() self:quickFix() end,
  }, mapping)
  self.hotkeys = mapping
  return self
end

-- Use another letter for the hotkeys, from now on: Hammerspoon keeps it across restarts.
function obj:_setHotkeyLetter(letter)
  if type(letter) ~= "string" or not letter:match("^[a-z0-9]$") or not self.hotkeySpec then return end
  hs.settings.set(LETTER_SETTING, letter)
  self:bindHotkeys(self.hotkeySpec) -- replaces the hotkeys bound before
end

--- Penwise:start()
--- Method
--- Adds the Penwise icon to the menu bar, so every action is a click away.
function obj:start()
  -- Penwise should work after a restart, and it can't read or paste text without Accessibility:
  -- start Hammerspoon at login, and let macOS ask for the permission now rather than at the hotkey.
  hs.autoLaunch(true)
  local allowed = hs.accessibilityState(true)
  if self.background then
    hs.menuIcon(false)
    hs.dockIcon(false)
    -- Hammerspoon opens its own preferences until it has the permission; Penwise's window asks.
    if not allowed and hs.closePreferences then hs.timer.doAfter(0.2, function() hs.closePreferences() end) end
  end
  -- When you turn the permission on, the settings window says so.
  local yours = hs.accessibilityStateCallback
  hs.accessibilityStateCallback = function(...)
    if yours then yours(...) end
    if self.webview then self:_send(hs.json.encode({ type = "access", allowed = hs.accessibilityState() })) end
  end
  if self.showMenu and not self.menu then
    self.menu = hs.menubar.new()
    self.menu:setTitle("✎")
    self.menu:setTooltip("Penwise")
    self.menu:setMenu(function() return self:_menuItems() end)
  end
  if self.checkForUpdates and not self.updateTimer then
    self.firstUpdateCheck = hs.timer.doAfter(30, function() self:_checkForUpdate() end)
    self.updateTimer = hs.timer.doEvery(24 * 3600, function() self:_checkForUpdate() end)
  end
  -- The first time, open the settings: Penwise needs a model before it can do anything.
  self.setupTask = hs.task.new(self.bin, function(_, stdout)
    local ok, data = pcall(hs.json.decode, stdout or "")
    if ok and type(data) == "table" then
      self.configured = data.configured
      if data.configured == false then self:showSettings() end
    end
  end, concat(self.args, { "settings" }))
  self.setupTask:start()
  return self
end

function obj:_checkForUpdate()
  self.updateTask = hs.task.new(self.bin, function(code, stdout)
    local ok, info = pcall(hs.json.decode, stdout or "")
    self.update = (code == 0 and ok and type(info) == "table" and info.available) and info.detail or nil
    if self.menu then self.menu:setTitle(self.update and "✎•" or "✎") end
  end, concat(self.args, { "update", "--check", "--json" }))
  self.updateTask:start()
end

--- Penwise:stop()
--- Method
--- Removes the menu bar icon.
function obj:stop()
  if self.menu then
    self.menu:delete()
    self.menu = nil
  end
  if self.updateTimer then
    self.updateTimer:stop()
    self.updateTimer = nil
  end
  return self
end

local MODIFIER_SYMBOLS = { ctrl = "⌃", alt = "⌥", shift = "⇧", cmd = "⌘" }

-- "⌃⌥P" for { { "ctrl", "alt" }, "p" }
local function hotkeyLabel(spec)
  if not spec then return "" end
  local label = ""
  for _, name in ipairs({ "ctrl", "alt", "shift", "cmd" }) do
    for _, mod in ipairs(spec[1]) do
      if mod == name then label = label .. MODIFIER_SYMBOLS[name] end
    end
  end
  return label .. string.upper(spec[2])
end

function obj:_menuItems()
  local keys = self.hotkeys or {}
  local function action(title, name, fn)
    local label = hotkeyLabel(keys[name])
    return { title = label ~= "" and (title .. "    " .. label) or title, fn = fn }
  end
  local items = {}
  if self.update then
    table.insert(items, { title = "Update Penwise (" .. self.update .. ")…", fn = function() self:_openInTerminal("update") end })
    table.insert(items, { title = "-" })
  end
  for _, item in ipairs({
    action("Check text", "fix", function() self:check("fix") end),
    action("Improve text", "improve", function() self:check("improve") end),
    action("Quick fix", "quick", function() self:quickFix() end),
    { title = "-" },
    { title = "Your recurring fixes…", fn = function() self:showInsights() end },
    { title = "Try it on a practice note", fn = function() self:_runQuietly("try") end },
    { title = "Settings…", fn = function() self:showSettings() end },
    { title = "Check my setup…", fn = function() self:checkSetup() end },
    { title = "-" },
    { title = "Uninstall Penwise…", fn = function() self:showUninstall() end },
  }) do
    table.insert(items, item)
  end
  return items
end

--- Penwise:showInsights()
--- Method
--- Shows the fixes you make most often, in the Penwise panel.
function obj:showInsights()
  self:_showView("Your recurring fixes", "insights", { "insights", "--json" })
end

--- Penwise:showSettings()
--- Method
--- Shows the settings: where the model runs, the API key and the model.
function obj:showSettings()
  self:_showView("Settings", "settings", { "settings" })
end

--- Penwise:checkSetup()
--- Method
--- Checks each part of Penwise (settings, model, hotkey) and shows what it found in the panel.
function obj:checkSetup()
  self:_showView("Check my setup", "note", { "doctor" }, "Checking each part…")
end

-- Show the panel in the middle of the screen with what `penwise <command>` prints: JSON for a
-- view of the given type, or plain text for a "note". It stays open when you switch apps (to
-- copy an API key, say).
function obj:_showView(title, view, command, waiting)
  self:_showWindow()
  self:_send(hs.json.encode({ type = "note", title = title, text = waiting or "Loading…" }))
  self.viewTask = hs.task.new(self.bin, function(_, stdout, stderr)
    if view == "note" then
      local text = ((stdout or "") .. (stderr or "")):gsub("%s+$", "")
      return self:_send(hs.json.encode({ type = "note", title = title, text = text }))
    end
    local ok, data = pcall(hs.json.decode, stdout or "")
    if ok and type(data) == "table" then
      data.type = view
      if view == "settings" then
        self.configured = data.configured
        data.access = hs.accessibilityState()
        local keys = self.hotkeys or {}
        data.hotkey = hotkeyLabel(keys.fix) -- what to press once it works
        data.hotkeys = { fix = hotkeyLabel(keys.fix), improve = hotkeyLabel(keys.improve), quick = hotkeyLabel(keys.quick) }
      end
      self:_send(hs.json.encode(data))
    else
      self:_send(hs.json.encode({ type = "note", title = title, text = stderr or "" }))
    end
  end, concat(self.args, command))
  self.viewTask:start()
end

-- The panel in the middle of the screen, as a window that stays open when you switch apps.
function obj:_showWindow()
  self.target = hs.window.focusedWindow()
  self.app = hs.application.frontmostApplication() -- to go back to when you close it
  self.fullScreen = self.target ~= nil and self.target:isFullScreen() == true
  self.anchors = nil
  self:_showPanel()
  self.keepOpen = true
end

--- Penwise:showUninstall()
--- Method
--- Asks whether to remove Penwise (and Hammerspoon, when the installer put it there for Penwise).
function obj:showUninstall()
  self:_showWindow()
  self:_send(hs.json.encode({ type = "uninstall", hammerspoon = self.background == true }))
end

-- Remove Penwise: `penwise uninstall` deletes its files and itself; Hammerspoon, if it stays,
-- no longer starts at login for Penwise, shows its own icon again, and reloads without Penwise.
function obj:_uninstall(withHammerspoon)
  self:_send(hs.json.encode({ type = "note", title = "Uninstall Penwise", text = "Removing Penwise…" }))
  if self.background then
    hs.autoLaunch(false)
    if not withHammerspoon then hs.menuIcon(true) end
  end
  local args = { "uninstall", "--yes" }
  if withHammerspoon then table.insert(args, "--hammerspoon") end -- it quits Hammerspoon last
  self.uninstallTask = hs.task.new(self.bin, function(code)
    self:_close()
    self:stop()
    hs.alert.show(code == 0 and "Penwise is uninstalled." or "Penwise couldn't remove everything.", 4)
    if not withHammerspoon then hs.timer.doAfter(1, function() hs.reload() end) end
  end, concat(self.args, args))
  self.uninstallTask:start()
end

-- Save the settings from the settings view, then show whether the model works. They go to
-- `penwise` in an environment variable: unlike arguments, other users' programs can't see it.
-- Steps that take a while (starting Ollama, downloading a model) come first, a line each.
function obj:_saveSettings(values)
  local output, buffer = "", ""
  local task = hs.task.new(self.bin, function(_, stdout, stderr)
    output = output .. "\n" .. (stdout or "")
    local data -- the last line that isn't a step
    for line in output:gmatch("[^\n]+") do
      local ok, event = pcall(hs.json.decode, line)
      if ok and type(event) == "table" and event.type ~= "progress" then data = event end
    end
    if not data then
      data = { saved = false, ok = false, message = (stderr ~= "" and stderr) or "Penwise couldn't save the settings." }
    end
    data.type = "saved"
    if data.saved then self.configured = true end
    self:_send(hs.json.encode(data))
  end, function(_, stdout)
    output = output .. (stdout or "")
    local lines
    lines, buffer = takeLines(buffer .. (stdout or ""))
    for _, line in ipairs(lines) do
      local ok, event = pcall(hs.json.decode, line)
      if ok and type(event) == "table" and event.type == "progress" then
        self:_send(hs.json.encode({ type = "saving", text = event.text }))
      end
    end
    return true
  end, concat(self.args, { "settings", "--save" }))
  local environment = task:environment()
  environment.PENWISE_SETTINGS = hs.json.encode(values)
  task:setEnvironment(environment)
  self.saveTask = task
  task:start()
end

-- Run a penwise command that needs no answer and shows nothing.
function obj:_runQuietly(subcommand)
  self.quietTask = hs.task.new(self.bin, nil, concat(self.args, { subcommand }))
  self.quietTask:start()
end

-- Open Terminal and run a penwise command there (for the interactive ones).
function obj:_openInTerminal(subcommand)
  local words = { "'" .. self.bin .. "'" }
  for _, arg in ipairs(self.args) do table.insert(words, arg) end
  table.insert(words, subcommand)
  hs.osascript.applescript(
    'tell application "Terminal"\n  activate\n  do script "' .. table.concat(words, " ") .. '"\nend tell'
  )
end

--- Penwise:check(mode)
--- Method
--- Reads the selected text in the frontmost app and opens the review panel.
function obj:check(mode)
  -- No model chosen yet (the welcome window was closed): open it again, rather than an error.
  if self.configured == false then return self:showSettings() end
  -- In the panel itself, the hotkey switches the mode. From an app, it checks that app's text.
  if self:_panelInFront() then
    self:_review(self.text, mode)
    return
  end
  self:_close()
  self:_withSelection(function(text)
    self:_showPanel()
    self:_review(text, mode)
  end)
end

function obj:_panelInFront()
  if not (self.webview and self.webview:isVisible()) then return false end
  local front = hs.application.frontmostApplication()
  return front ~= nil and front:bundleID() == HAMMERSPOON
end

--- Penwise:quickFix()
--- Method
--- Fixes the selected text and replaces it right away, then says briefly what changed.
function obj:quickFix()
  if self.configured == false then return self:showSettings() end
  self:_withSelection(function(text)
    self.text = text
    local notice = hs.alert.show("Penwise: fixing…", 60)
    self:_run(text, "fix", { "--no-explain" }, function(event)
      if event.type ~= "result" and event.type ~= "error" then return end
      hs.alert.closeSpecific(notice)
      if event.type == "error" then
        hs.alert.show("Penwise: " .. event.message, 6)
      else
        -- Changes to numbers, citations, acronyms, math, code or links are left out.
        local applied, held = {}, 0
        for _, change in ipairs(event.changes) do
          if change.risk then held = held + 1 else table.insert(applied, change) end
        end
        local note = held > 0 and string.format("  · %d left for you to review (⌃⌥P)", held) or ""
        if #applied == 0 then
          hs.alert.show("Penwise: looks good, nothing to fix" .. note, 3)
        elseif self.source.kind == "readonly" then
          self:_replace(event.edited, applied)
          hs.alert.show("Penwise: " .. summarize(applied) .. ", copied: paste it with ⌘V" .. note, 4)
        else
          self:_replace(event.edited, applied)
          local undo = self.source.kind == "terminal" and "" or "  (⌘Z to undo)"
          hs.alert.show("Penwise: " .. summarize(applied) .. undo .. note, 3)
        end
      end
    end)
  end)
end

-- Read the selection, check it is usable, and pass it on.
function obj:_withSelection(callback)
  if not hs.fs.attributes(self.bin) then
    hs.alert.show("Penwise: command not found at " .. self.bin .. ". Run `penwise setup` again.")
    return
  end
  -- Without Accessibility permission, Hammerspoon can't read your text or paste the fix.
  if not hs.accessibilityState(true) then
    hs.alert.show("Penwise: turn on Hammerspoon in System Settings → Privacy & Security → Accessibility", 6)
    return
  end
  if self:_panelInFront() then return end -- no app text to read
  local app = hs.application.frontmostApplication()
  if app and app:bundleID() == HAMMERSPOON then return end
  self.target = hs.window.focusedWindow()
  self.style = nil -- Improve's tone, when chosen in the panel
  self.app = app
  -- Where the text is going (an email, a chat) sets the tone of "improve".
  self.context = {
    "--app", (app and app:bundleID()) or "",
    "--window", (self.target and self.target:title()) or "",
  }
  self.fullScreen = self.target ~= nil and self.target:isFullScreen() == true
  -- One read at a time: a second press while copying would see the clipboard being put back.
  local now = hs.timer.secondsSinceEpoch()
  if self.readingSince and now - self.readingSince < 3 then return end
  self.readingSince = now
  self:_log("hotkey in %s%s", (app and app:bundleID()) or "?", self.fullScreen and " (full screen)" or "")
  self:_readSelection(function(text)
    self.readingSince = nil
    if not text or not text:find("%S") then
      if TERMINALS[app and app:bundleID()] then
        hs.alert.show("Penwise: nothing typed here: select the text to check")
      else
        hs.alert.show("Penwise: click in a text box, or select the text to check")
      end
    elseif #text > 100000 then
      hs.alert.show("Penwise: the selection is too long (over 100,000 characters)")
    else
      callback(text)
    end
  end)
end

local TEXT_FIELD_ROLES = { AXTextArea = true, AXTextField = true, AXComboBox = true }

local function attribute(element, name)
  local ok, value = pcall(function() return element:attributeValue(name) end)
  if ok then return value end
end

-- Whether the app lets you edit this text: text boxes yes (some apps report rich-text boxes as
-- not settable, so their word is taken); anything else (a web page, a PDF) only if it says so.
local function editable(element)
  if TEXT_FIELD_ROLES[attribute(element, "AXRole")] then return true end
  local ok, settable = pcall(function() return element:isAttributeSettable("AXValue") end)
  return not (ok and settable == false)
end

local function hasText(value)
  return type(value) == "string" and value:find("%S") ~= nil
end

-- A selection in a terminal can include the frame Claude Code and other tools draw around their
-- input box, the prompt, and line breaks where long lines wrap: keep only what you typed.
local PROMPTS = {
  "^➜%s+%S+%s+git:%b()%s+✗%s+", -- oh-my-zsh's default: ➜  penwise git:(main) ✗
  "^➜%s+%S+%s+git:%b()%s+", -- ➜  penwise git:(main)
  "^➜%s+%S+%s+", -- ➜  ~
  "^%S+@%S+ .-[%%%$#]%s+", -- macOS zsh: me@mac ~ %
  "^%S+@[^%s:]+:%S-[%$#]%s+", -- bash: me@host:~/dir$
  "^[~/]%S*%s+[%%%$#]%s+", -- ~/dir %
  "^>%s+", "^❯%s+", "^›%s+", "^»%s+", "^λ%s+", "^→%s+", "^▶%s+", "^%$%s+", "^%%%s+", "^#%s+",
}

local BOX = "\226[\148\149][\128-\191]" -- box drawing characters (─ │ ╭ ╯ …), U+2500–U+257F

local function isBorder(line)
  local rest, count = line:gsub(BOX, "")
  return count >= 3 and not rest:find("%S")
end

-- With nothing selected in a terminal: what you're typing, at the bottom of the window. That is
-- the input box of Claude Code or Codex (a line starting with > ❯ › or ▌, and the lines
-- under it up to the box's edge), or else the last line: the shell's command line.
-- Returns the text, and its first and last byte in `buffer` (to put the panel above it).
local function terminalTyping(buffer)
  -- The end of a long scrollback is enough: the lines of its last 20,000 bytes.
  local lines, starts = {}, {}
  local position = 1
  if #buffer > 20000 then position = (buffer:find("\n", #buffer - 20000, true) or #buffer) + 1 end
  while position <= #buffer do
    local newline = buffer:find("\n", position, true) or #buffer + 1
    table.insert(lines, (buffer:sub(position, newline - 1):gsub("\r$", "")))
    table.insert(starts, position)
    position = newline + 1
  end
  local last = #lines
  while last > 0 and not lines[last]:find("%S") do last = last - 1 end
  if last == 0 then return "" end
  local first, final = last, last
  for i = last, math.max(1, last - 12), -1 do
    local plain = lines[i]:gsub(BOX, "")
    if plain:find("^%s*>%s") or plain:find("^%s*❯%s") or plain:find("^%s*›%s") or plain:find("^%s*▌") then
      first, final = i, i
      for j = i + 1, last do
        if isBorder(lines[j]) or not lines[j]:gsub(BOX, ""):find("%S") then break end
        final = j
      end
      break
    end
  end
  local block = {}
  for i = first, final do table.insert(block, lines[i]) end
  return table.concat(block, "\n"), starts[first], starts[final] + #lines[final] - 1
end

local function terminalInput(text)
  text = text:gsub(BOX, "")
  local lines = {}
  for line in (text .. "\n"):gmatch("(.-)\r?\n") do
    line = line:match("^%s*(.-)%s*$")
    if line ~= "" then table.insert(lines, line) end
  end
  text = table.concat(lines, " ") .. " " -- the space lets a prompt with nothing after it match
  for _, prompt in ipairs(PROMPTS) do
    local rest = text:gsub(prompt, "", 1)
    if rest ~= text then return (rest:gsub("%s+$", "")) end
  end
  return (text:gsub("%s+$", ""))
end

-- macOS counts text in UTF-16 units; Lua strings count bytes (UTF-8).
local function utf16Length(text)
  local units = 0
  for _, code in utf8.codes(text) do units = units + (code > 0xFFFF and 2 or 1) end
  return units
end

-- The byte index of the character `units` UTF-16 units into `text`.
local function byteIndex(text, units)
  local count = 0
  for position, code in utf8.codes(text) do
    if count >= units then return position end
    count = count + (code > 0xFFFF and 2 or 1)
  end
  return #text + 1
end

-- The first and last byte of the block of `text` around byte `at`, with blocks split
-- at `separator` and surrounding whitespace left out. Nil on an empty block.
local function blockAt(text, at, separator)
  local first = 1
  while true do
    local from, to = text:find(separator, first)
    if not from or at <= from then
      local last = from and from - 1 or #text
      first = text:find("%S", first)
      if not first or first > last then return nil end
      return first, first + #text:sub(first, last):match("^(.-)%s*$") - 1
    end
    first = to + 1
  end
end

-- The paragraph at byte `at`: the lines between blank lines, or only the line itself
-- when that block is longer than `limit` (in documents without blank lines).
local function paragraphAt(text, at, limit)
  local first, last = blockAt(text, at, "[\r\n]%s*[\r\n]")
  if first and last - first >= limit then first, last = blockAt(text, at, "[\r\n]") end
  return first, last
end

-- A rectangle on screen, or nil when `x`, `y`, `w` and `h` aren't all numbers.
local function rect(x, y, w, h)
  for _, value in ipairs({ x, y, w, h }) do
    if type(value) ~= "number" then return nil end
  end
  if h > 0 then return { x = x, y = y, w = w, h = h } end
end

local function frameOf(element)
  local position, size = attribute(element, "AXPosition"), attribute(element, "AXSize")
  if type(position) == "table" and type(size) == "table" then
    return rect(position.x, position.y, size.w, size.h)
  end
end

-- Where the text in `range` is on screen (by default, the selected text).
local function selectionBounds(element, range)
  range = range or attribute(element, "AXSelectedTextRange")
  if type(range) ~= "table" then return nil end
  local ok, bounds = pcall(function() return element:parameterizedAttributeValue("AXBoundsForRange", range) end)
  if ok and type(bounds) == "table" then return rect(bounds.x, bounds.y, bounds.w, bounds.h) end
end

-- The same text, give or take spacing and line breaks (apps report those differently).
local function sameText(a, b)
  local function squeeze(text) return (text:gsub("%s+", " "):gsub("^ ", ""):gsub(" $", "")) end
  return type(a) == "string" and type(b) == "string" and squeeze(a) == squeeze(b)
end

-- Where the panel may go, best first: next to the text being checked, so you can compare,
-- without covering it. That is the whole text box when it's checked whole; the paragraph, your
-- selection, or the line you're typing in a terminal; then a small text box; the cursor's line;
-- and in an app that doesn't say where its text is (WeChat), the mouse pointer, as you most
-- likely just clicked there. Returns the places, and the first one's name for the log.
function obj:_anchorsFor(element, kind, range)
  local places, names = {}, {}
  local function add(place, name)
    if place then
      table.insert(places, place)
      table.insert(names, name)
    end
  end
  local frame = element and frameOf(element)
  if kind == "field" then add(frame, "the text box") end
  if range then add(element and selectionBounds(element, range), "the text") end
  if frame and frame.h <= 200 then add(frame, "the text box") end
  add(element and selectionBounds(element), "the cursor's line")
  local mouse = hs.mouse.absolutePosition()
  local window = self.target and self.target:frame()
  if mouse and window and mouse.x >= window.x and mouse.x <= window.x + window.w
    and mouse.y >= window.y and mouse.y <= window.y + window.h then
    add({ x = mouse.x - 24, y = mouse.y - 14, w = 0, h = 28 }, "the mouse pointer")
  end
  return places, names[1] or "the middle of the screen"
end

-- Roles of things that aren't text: with nothing selected there, Penwise doesn't select all.
local NOT_TEXT_ROLES = { AXList = true, AXOutline = true, AXTable = true, AXBrowser = true, AXButton = true, AXImage = true }

-- Ask the app for its selected text. With nothing selected, use the whole text box if it is
-- short, or else the paragraph at the cursor; in a terminal, what you're typing. If the app
-- doesn't tell (WeChat, Codex, ...), copy the selection with ⌘C, or select all in the text box
-- and copy that. `self.source` remembers where the text came from, so Replace can select it
-- again; text that can't be edited (a web page) is "readonly" and gets copied.
function obj:_readSelection(callback, lookedAgain)
  local element = attribute(hs.axuielement.systemWideElement(), "AXFocusedUIElement")
  local bundle = self.app and self.app:bundleID()
  local terminal = TERMINALS[bundle] == true
  local role = element and attribute(element, "AXRole")
  local readonly = not terminal and element ~= nil and not editable(element)
  local function use(text, source, how, range)
    if terminal then
      text, source = terminalInput(text), { kind = "terminal" }
    end
    self.source = source
    local where
    self.anchors, where = self:_anchorsFor(element, source.kind, range or source.range)
    self:_log("read: %s, %s, %s, %d characters; panel by %s", how, tostring(role), source.kind, #text, where)
    callback(text)
  end
  if element then
    local selected = attribute(element, "AXSelectedText")
    if hasText(selected) then
      local range = attribute(element, "AXSelectedTextRange")
      return use(selected, { kind = readonly and "readonly" or "selection", element = element, range = range }, "selection")
    end
    local value = attribute(element, "AXValue")
    if terminal and hasText(value) then
      local typed, first, last = terminalTyping(value)
      local range
      if first then
        pcall(function()
          range = { location = utf16Length(value:sub(1, first - 1)), length = utf16Length(value:sub(first, last)) }
        end)
      end
      return use(typed, {}, "what you're typing", range)
    end
    if not terminal and self.wholeFieldLimit > 0 and TEXT_FIELD_ROLES[role] and hasText(value) then
      if #value <= self.wholeFieldLimit then
        return use(value, { kind = "field", element = element }, "whole text box")
      end
      local paragraph, range = self:_paragraphAtCursor(element, value)
      if paragraph then
        return use(paragraph, { kind = "paragraph", element = element, range = range }, "paragraph")
      end
    end
  end
  if not lookedAgain and not terminal and self.app and not hasText(element and attribute(element, "AXValue")) then
    -- Electron apps (Claude, Slack, ...) and Chromium browsers describe their text boxes to other
    -- apps only when asked to. Ask, give the app a moment, and look again.
    local asked = false
    local names = CHROMIUM_BROWSERS[bundle] and { "AXManualAccessibility", "AXEnhancedUserInterface" }
      or { "AXManualAccessibility" }
    for _, name in ipairs(names) do
      local ok, result = pcall(function()
        return hs.axuielement.applicationElement(self.app):setAttributeValue(name, true)
      end)
      asked = asked or (ok and result ~= nil)
    end
    if asked then
      self:_log("asked %s to describe its text boxes; looking again", tostring(bundle))
      self.lookAgainTimer = hs.timer.doAfter(0.3, function() self:_readSelection(callback, true) end)
      return
    end
  end

  -- Copy the selection. Wait until you let go of the hotkey: with ⌃⌥ still down, ⌘C would
  -- arrive as ⌃⌥⌘C, and most apps wouldn't copy.
  self:_whenKeysReleased(function()
    self:_copy(function(text)
      if text then return use(text, { kind = readonly and "readonly" or "copy" }, "copied with ⌘C") end
      if terminal or readonly or NOT_TEXT_ROLES[role] or bundle == "com.apple.finder" then
        self:_log("read: nothing selected to copy")
        return callback(nil)
      end
      -- Nothing selected, in a text box the app doesn't describe: select all in it and copy.
      hs.eventtap.keyStroke({ "cmd" }, "a", 0)
      self:_copy(function(all)
        if all and #all <= self.wholeFieldLimit then
          return use(all, { kind = "copyall" }, "selected all and copied")
        end
        if all then hs.eventtap.keyStroke({}, "right", 0) end -- too much: not a text box; deselect
        self:_log("read: nothing to copy here%s", all and " (select all gave too much)" or "")
        callback(nil)
      end)
    end)
  end)
end

-- Press ⌘C and call back with what it copied (or nil), leaving the clipboard as it was.
function obj:_copy(callback)
  local saved = hs.pasteboard.readAllData()
  local count = hs.pasteboard.changeCount()
  local started = hs.timer.secondsSinceEpoch()
  hs.eventtap.keyStroke({ "cmd" }, "c", 0)
  local timer
  timer = hs.timer.doEvery(0.02, function()
    local copied = hs.pasteboard.changeCount() ~= count
    if copied or hs.timer.secondsSinceEpoch() - started > 0.5 then
      timer:stop()
      local text = copied and hs.pasteboard.getContents() or nil
      restoreClipboard(saved)
      callback(hasText(text) and text or nil)
    end
  end)
  self.copyTimer = timer
end

-- Call `fn` once no modifier key is held down (or after a second).
function obj:_whenKeysReleased(fn)
  local function held()
    local keys = hs.eventtap.checkKeyboardModifiers()
    return keys.ctrl or keys.alt or keys.cmd or keys.shift
  end
  if not held() then return fn() end
  local started = hs.timer.secondsSinceEpoch()
  self.keysTimer = hs.timer.doEvery(0.02, function()
    if not held() or hs.timer.secondsSinceEpoch() - started > 1 then
      self.keysTimer:stop()
      fn()
    end
  end)
end

-- The paragraph at the cursor: its text and its range (in UTF-16 units, as macOS counts).
function obj:_paragraphAtCursor(element, value)
  local ok, text, range = pcall(function()
    local cursor = attribute(element, "AXSelectedTextRange")
    local units = type(cursor) == "table" and (cursor.location or cursor.loc)
    if not units then return nil end
    local first, last = paragraphAt(value, byteIndex(value, units), self.wholeFieldLimit)
    if not first then return nil end
    local text = value:sub(first, last)
    return text, { location = utf16Length(value:sub(1, first - 1)), length = utf16Length(text) }
  end)
  if ok and text then return text, range end
end

-- Where the panel goes: just above a place, lined up with its left edge, or just below it when
-- there is no room above; at full size if possible, or else shrunk to the bigger side (it scrolls)
-- rather than covering the text. In the middle of the screen only when no place has room.
local GAP, MIN_HEIGHT, MIN_WIDTH, MAX_WIDTH = 12, 150, 480, 900

local function placePanel(places, size, area)
  local function at(place, shrink)
    local x = math.max(area.x + GAP, math.min(place.x, area.x + area.w - size.w - GAP))
    local above = place.y - GAP - area.y
    local below = area.y + area.h - (place.y + place.h + GAP)
    if size.h <= above then return { x = x, y = place.y - GAP - size.h, h = size.h } end
    if size.h <= below then return { x = x, y = place.y + place.h + GAP, h = size.h } end
    if shrink and math.max(above, below) >= MIN_HEIGHT then
      if above >= below then return { x = x, y = area.y, h = above } end
      return { x = x, y = place.y + place.h + GAP, h = below }
    end
  end
  for _, shrink in ipairs({ false, true }) do
    for _, place in ipairs(places) do
      local spot = at(place, shrink)
      if spot then return spot end
    end
  end
  return { x = area.x + (area.w - size.w) / 2, y = area.y + (area.h - size.h) / 3, h = size.h }
end

function obj:_showPanel()
  if not self.webview then
    local content = hs.webview.usercontent.new("penwise")
    content:setCallback(function(message) self:_onMessage(message.body) end)
    self.ready = false
    -- A popover: no title bar; the page draws the rounded panel on a transparent window. Like
    -- Spotlight, it takes the keyboard without bringing Hammerspoon forward ("nonactivating"),
    -- so macOS doesn't switch away from an app in full screen.
    local masks = hs.webview.windowMasks
    self.webview = hs.webview.new({ x = 0, y = 0, w = PANEL_WIDTH, h = self.panelHeight }, {}, content)
      :windowStyle(masks.borderless | (masks.nonactivating or 0))
      :transparent(true)
      :shadow(true)
      :windowTitle("Penwise")
      :allowTextEntry(true)
      :level(hs.drawing.windowLevels.floating)
      -- Show on the current Space, also over apps in full screen.
      :behavior(hs.drawing.windowBehaviors.canJoinAllSpaces | hs.drawing.windowBehaviors.fullScreenAuxiliary)
      :windowCallback(function(action, _, hasFocus)
        if action == "closing" then
          self:_close()
          self:_returnToApp(function() self:_deselect() end)
        elseif action == "focusChange" then
          -- These arrive a moment late, so a panel hidden and shown again at once can hear its
          -- own "lost focus" after "got focus". Close only if it's still unfocused a bit later.
          self.panelFocused = hasFocus == true
          if not hasFocus then
            local shown = self.shownCount
            self.blurTimer = hs.timer.doAfter(0.2, function()
              if not self.panelFocused and not self.keepOpen and self.shownCount == shown and self.webview:isVisible() then
                self:_log("panel lost focus: closed")
                self:_close() -- you clicked somewhere else: get out of the way
              end
            end)
          end
        end
      end)
      :html(self.html)
  end
  self:_placePanel()
  -- show() makes the panel the key window, and a nonactivating panel takes the keyboard without
  -- bringing Hammerspoon forward: the app you're writing in stays active (so it keeps its text
  -- box and selection), macOS doesn't switch away from a full-screen app, and no other
  -- Hammerspoon window (like the console) can take the keyboard.
  self.shownCount = (self.shownCount or 0) + 1
  self.webview:show()
  self:_log("panel shown%s", self.fullScreen and " over a full-screen app" or "")
end

-- Size the panel to fit its content, and put it next to the text being checked. It is as
-- wide as the text field, within limits.
function obj:_placePanel()
  local screen = (self.target and self.target:screen()) or hs.screen.mainScreen()
  local area = screen:frame()
  local places = self.anchors or {}
  -- As wide as the text box (within limits), so the panel lines up with it.
  local width = places[1] and math.max(MIN_WIDTH, math.min(MAX_WIDTH, places[1].w)) or PANEL_WIDTH
  local size = { w = width, h = math.max(MIN_HEIGHT, math.min(area.h * 0.7, self.panelHeight)) }
  local spot = placePanel(places, size, area)
  self.webview:frame({ x = spot.x, y = spot.y, w = size.w, h = spot.h })
end

-- Check the text and stream the results into the review panel.
function obj:_review(text, mode)
  self.text, self.mode = text, mode
  self.keepOpen = false -- a check closes when you click elsewhere
  local readonly = self.source ~= nil and self.source.kind == "readonly"
  self:_send(hs.json.encode({ type = "begin", original = text, mode = mode, readonly = readonly or nil }))
  self:_run(text, mode, {}, function(_, line) self:_send(line) end)
end

-- Run `penwise check` and call onEvent(event, line) for each JSON event it prints.
function obj:_run(text, mode, extraArgs, onEvent)
  self.run = self.run + 1
  local run = self.run
  if self.task and self.task:isRunning() then self.task:terminate() end

  local buffer, seen, finished = "", {}, false
  local function forward(lines)
    for _, line in ipairs(lines) do
      local ok, event = pcall(hs.json.decode, line)
      if not seen[line] and ok and type(event) == "table" then
        seen[line] = true
        finished = finished or event.type == "done" or event.type == "error"
        onEvent(event, line)
      end
    end
  end

  -- The text goes in as an argument, not on stdin: hs.task writes stdin later, from the
  -- event loop, so input given to a streaming task can be lost when stdin is closed.
  local args = concat(self.args, concat({ "check", "--format", "jsonl", "--mode", mode }, extraArgs))
  args = concat(args, self.context or {})
  if self.style then args = concat(args, { "--style", self.style }) end
  args = concat(args, { "--", text })
  self.task = hs.task.new(self.bin, function(code, stdout, stderr)
    if run ~= self.run then return end
    if not finished and stdout and stdout ~= "" then
      -- Depending on the Hammerspoon version, output not yet streamed arrives here.
      forward((takeLines(buffer .. stdout .. "\n")))
      forward((takeLines(stdout .. "\n")))
    end
    if not finished then
      local message = (stderr or ""):gsub("^penwise: ", ""):gsub("%s+$", "")
      if message == "" then message = "penwise stopped unexpectedly (exit code " .. code .. ")" end
      local event = { type = "error", message = message }
      onEvent(event, hs.json.encode(event))
    end
  end, function(_, stdout)
    if run ~= self.run then return false end
    local lines
    lines, buffer = takeLines(buffer .. (stdout or ""))
    forward(lines)
    return true
  end, args)

  self.task:start()
end

function obj:_send(json)
  if not self.ready then
    table.insert(self.queue, json)
  else
    self.webview:evaluateJavaScript("penwise.receive(" .. json .. ")")
  end
end

function obj:_onMessage(body)
  if body.action == "ready" then
    self.ready = true
    for _, json in ipairs(self.queue) do self:_send(json) end
    self.queue = {}
  elseif body.action == "size" then
    -- The panel's content needs `height`; the window adds its title bar to that. (A window
    -- resized meanwhile gives an odd difference: keep the last good one then.)
    local chrome = self.webview:frame().h - (body.viewport or 0)
    if chrome < 0 or chrome > 60 then chrome = self.chrome or 28 end
    self.chrome = chrome
    self.panelHeight = body.height + chrome
    if self.webview:isVisible() then self:_placePanel() end
  elseif body.action == "replace" then
    self:_replace(body.text, body.changes or {})
  elseif body.action == "copy" then
    hs.pasteboard.setContents(body.text)
    self:_close()
    self:_returnToApp(function() self:_deselect() end)
    hs.alert.show("Copied")
  elseif body.action == "mode" or body.action == "retry" then
    self:_review(self.text, body.mode)
  elseif body.action == "style" then
    self.style = body.style
    self:_review(self.text, "improve")
  elseif body.action == "keep" then
    self.keepTask = hs.task.new(self.bin, nil, concat(self.args, { "keep", "--", body.word }))
    self.keepTask:start()
  elseif body.action == "doctor" then
    self:checkSetup()
  elseif body.action == "settings" then
    self:showSettings()
  elseif body.action == "save-settings" then
    self:_setHotkeyLetter(body.hotkey)
    self:_saveSettings(body.settings)
  elseif body.action == "paste-key" then
    self:_send(hs.json.encode({ type = "pasted", text = hs.pasteboard.getContents() or "" }))
  elseif body.action == "uninstall" then
    self:_uninstall(body.hammerspoon == true)
  elseif body.action == "try" then
    self:_close()
    self:_runQuietly("try")
  elseif body.action == "open-url" then
    hs.urlevent.openURL(body.url)
  elseif body.action == "cancel" then
    self:_close()
    self:_returnToApp(function() self:_deselect() end)
  end
end

-- Put the accepted text in place of the original: back in the app, select the text that was
-- checked and paste over it. If it can't be selected, copy the fix instead: pasting then would
-- add it next to the original.
function obj:_replace(text, changes)
  self:_close()
  local kind = (self.source or {}).kind
  self:_log("replace: %s", tostring(kind))
  if kind == "readonly" then
    hs.pasteboard.setContents(text)
    self:_returnToApp()
  elseif kind == "terminal" then
    self:_returnToApp(function() self:_typeIntoTerminal(text) end, function() self:_copyInstead(text) end)
  elseif text ~= self.text then
    self:_returnToApp(function() self:_pasteOver(text) end, function() self:_copyInstead(text) end)
  else
    self:_returnToApp(function() self:_deselect() end)
  end
  if #changes > 0 then
    -- As an argument, like the text in _run: input written to stdin can be lost.
    local json = hs.json.encode({ changes = changes })
    self.recordTask = hs.task.new(self.bin, nil, concat(self.args, { "record", "--", json }))
    self.recordTask:start()
  end
end

-- After pasting, read the text box again and say in the hotkey log whether the whole fix is
-- there: how much of it is, and the punctuation mark that went missing, never your words.
local function checkPasted(self, text)
  local element = (self.source or {}).element
  if not element then return end
  local ok, value = pcall(function() return element:attributeValue("AXValue") end)
  if not ok or type(value) ~= "string" or #value > 200000 then
    return self:_log("after pasting: couldn't read the text box again")
  end
  if value:find(text, 1, true) then return self:_log("after pasting: the text box has the fix") end
  -- The longest start of the fix that is in the box (if a start is there, so is any shorter one).
  local found, missing = 0, #text
  while found < missing do
    local middle = math.floor((found + missing + 1) / 2)
    if value:find(text:sub(1, middle), 1, true) then found = middle else missing = middle - 1 end
  end
  local after = text:sub(found + 1, found + 1)
  self:_log("after pasting: the text box has %d of the fix's %d bytes%s", found, #text,
    after:match("^%p$") and string.format(", up to “%s”", after) or "")
end

local function paste(text, self)
  local saved = hs.pasteboard.readAllData()
  hs.pasteboard.setContents(text)
  hs.eventtap.keyStroke({ "cmd" }, "v", 0)
  self.restoreTimer = hs.timer.doAfter(1, function()
    checkPasted(self, text)
    restoreClipboard(saved)
  end)
end

-- Select the text that was checked, make sure it is selected, then paste the fix over it.
-- Ways to select, in order: for a whole text box ⌘A (every text box knows it), then through
-- Accessibility; for a paragraph or your selection, whatever is still selected, then through
-- Accessibility. If none works, the fix is copied instead: pasting would add it next to the text.
function obj:_pasteOver(text)
  local source = self.source or {}
  local element = source.element
  if source.kind == "copyall" then
    -- An app that doesn't describe its text box: select all in it again, as when reading.
    return self:_whenKeysReleased(function()
      hs.eventtap.keyStroke({ "cmd" }, "a", 0)
      self:_log("selected all (⌘A), pasted the fix")
      paste(text, self)
    end)
  end
  if not element then
    self:_log("pasted the fix over your selection")
    return paste(text, self)
  end
  local function selectRange(range)
    if type(range) == "table" then pcall(function() element:setAttributeValue("AXSelectedTextRange", range) end) end
  end
  local ways
  if source.kind == "field" then
    -- ⌘A selects all of the text box that has the keyboard. Page boxes in Chrome don't report
    -- what it selected, so unless the keyboard is in another text box, that is good enough.
    ways = { { "⌘A", function() hs.eventtap.keyStroke({ "cmd" }, "a", 0) end, 1.0, true } }
  else
    ways = {
      { "the selection already there", function() end, 0.15 },
      { "Accessibility", function() selectRange(source.range) end },
    }
  end
  local function try(n)
    local way = ways[n]
    if not way then return self:_copyInstead(text) end
    way[2]()
    self:_whenSelected(element, way[3] or 0.6, function(selected)
      if not selected and way[4] then
        local elsewhere, where = self:_keyboardElsewhere(element)
        self:_log("⌘A not confirmed by the app; the keyboard is in %s", where)
        selected = not elsewhere
      end
      if not selected then return try(n + 1) end
      self:_log("selected the text (%s), pasted the fix", way[1])
      paste(text, self)
    end)
  end
  self:_whenKeysReleased(function()
    self:_focusBox(element, function() try(1) end)
  end)
end

-- Give the keyboard back to the text box Penwise read. Through Accessibility first; if the app
-- put it somewhere else (Chrome's new tab page hands it to the address bar), click in the box,
-- as you would, and put the mouse pointer back.
function obj:_focusBox(element, done)
  pcall(function() element:setAttributeValue("AXFocused", true) end)
  self.focusTimer = hs.timer.doAfter(0.1, function()
    local elsewhere, where = self:_keyboardElsewhere(element)
    if not elsewhere then return done() end
    local box = frameOf(element)
    if not box then
      self:_log("the keyboard is in %s, and the text box's place is unknown", where)
      return done()
    end
    self:_log("the keyboard is in %s: clicking in the text box", where)
    local pointer = hs.mouse.absolutePosition()
    hs.eventtap.leftClick({ x = box.x + box.w / 2, y = box.y + box.h / 2 })
    if pointer then hs.mouse.absolutePosition(pointer) end
    self.focusTimer = hs.timer.doAfter(0.15, done)
  end)
end

-- Call done(true) once the app shows the checked text as selected, or done(false) after
-- `seconds`. Apps update this a moment after the selection changes (Chrome, Electron), so it
-- is checked a few times. An app that can't say what is selected counts as selected.
function obj:_whenSelected(element, seconds, done)
  local started = hs.timer.secondsSinceEpoch()
  if self.verifyTimer then self.verifyTimer:stop() end
  self.verifyTimer = hs.timer.doEvery(0.05, function()
    local selected = attribute(element, "AXSelectedText")
    local ok = selected == nil or sameText(selected, self.text)
    if ok or hs.timer.secondsSinceEpoch() - started > seconds then
      self.verifyTimer:stop()
      done(ok)
    end
  end)
end

-- Whether the keyboard is in a different text box (one that doesn't hold the checked text).
-- Whether the keyboard is in a text box other than `box`, the one Penwise read. The box itself
-- counts as yours whatever text it reports (a search box with suggestions open can report the
-- highlighted suggestion), and so does a box holding your text. Also says where, for the log.
function obj:_keyboardElsewhere(box)
  local focused = attribute(hs.axuielement.systemWideElement(), "AXFocusedUIElement")
  if not focused then return false, "nothing the app reports" end
  if box and focused == box then return false, "the text box" end
  local role, value = attribute(focused, "AXRole"), attribute(focused, "AXValue")
  local elsewhere = TEXT_FIELD_ROLES[role] == true and type(value) == "string" and not sameText(value, self.text)
  local holds = type(value) == "string" and string.format(" holding %d characters", #value) or ""
  return elsewhere, (elsewhere and "another " or "") .. tostring(role) .. holds
end

-- After a select-all for reading, put the cursor back at the end, so typing doesn't replace it all.
function obj:_deselect()
  if (self.source or {}).kind ~= "copyall" then return end
  self:_whenKeysReleased(function() hs.eventtap.keyStroke({}, "right", 0) end)
end

-- In a terminal: go to the end of the line you're typing, clear it, and paste the fix there.
function obj:_typeIntoTerminal(text)
  self:_whenKeysReleased(function()
    hs.eventtap.keyStroke({ "ctrl" }, "e", 0)
    hs.eventtap.keyStroke({ "ctrl" }, "u", 0)
    self:_log("cleared the line in the terminal, pasted the fix")
    paste(text, self)
  end)
end

function obj:_copyInstead(text)
  self:_log("couldn't select the text: copied the fix instead")
  hs.pasteboard.setContents(text)
  hs.alert.show("Penwise: couldn't select your text to replace it, so the fix is copied. Select your text and press ⌘V.", 6)
end

-- Go back to the app being edited. Once it is in front again (Electron apps can take a moment),
-- call `fn`; if it doesn't come back within 2 seconds, call `fallback` instead.
function obj:_returnToApp(fn, fallback)
  if self.app then self.app:activate() end
  if self.target then self.target:focus() end
  if not fn then return end
  local started = hs.timer.secondsSinceEpoch()
  if self.returnTimer then self.returnTimer:stop() end
  self.returnTimer = hs.timer.doEvery(0.05, function()
    local front = hs.application.frontmostApplication()
    local back = not self.app or (front ~= nil and front:pid() == self.app:pid())
    if back or hs.timer.secondsSinceEpoch() - started > 2 then
      self.returnTimer:stop()
      -- A moment more for the app to give the keyboard back to its text box.
      self:_log(back and "back in the app" or "the app didn't come back to the front")
      self.settleTimer = hs.timer.doAfter(0.1, function()
        if back then fn() elseif fallback then fallback() end
      end)
    end
  end)
end

-- Hide the panel and ignore a check that is still running.
function obj:_close()
  self.panelFocused = false
  self.keepOpen = false
  self.run = self.run + 1
  if self.task and self.task:isRunning() then self.task:terminate() end
  if self.webview then self.webview:hide() end
end

return obj
