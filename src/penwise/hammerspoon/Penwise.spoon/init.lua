--- === Penwise ===
---
--- Select text in any app, press a hotkey, and review suggested English fixes,
--- each with a short note. Press Return to replace your selection.
---
--- Requires the `penwise` command: https://github.com/LuckyLetter/penwise

local obj = {}
obj.__index = obj

obj.name = "Penwise"
obj.version = "0.4.1"
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

--- Penwise.logFile
--- Variable
--- A log of what the hotkey did, step by step (never your text), which `penwise doctor` shows
--- when something doesn't work. Set to nil to keep no log.
obj.logFile = os.getenv("HOME") .. "/Library/Logs/penwise-hotkey.log"

obj.logger = hs.logger.new("Penwise")

local PANEL_WIDTH = 640
local HAMMERSPOON = "org.hammerspoon.Hammerspoon"

-- Terminals show past commands and output as one big text area, and a paste there types at the
-- prompt instead of replacing anything. So only a selection is checked, and the fix is copied.
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
function obj:bindHotkeys(mapping)
  hs.spoons.bindHotkeysToSpec({
    fix = function() self:check("fix") end,
    improve = function() self:check("improve") end,
    quick = function() self:quickFix() end,
  }, mapping)
  self.hotkeys = mapping
  return self
end

--- Penwise:start()
--- Method
--- Adds the Penwise icon to the menu bar, so every action is a click away.
function obj:start()
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
    { title = "Settings…", fn = function() self:_openInTerminal("setup") end },
    { title = "Check my setup…", fn = function() self:_openInTerminal("doctor") end },
  }) do
    table.insert(items, item)
  end
  return items
end

--- Penwise:showInsights()
--- Method
--- Shows the fixes you make most often, in the Penwise panel.
function obj:showInsights()
  self.target = hs.window.focusedWindow()
  self.app = hs.application.frontmostApplication() -- to go back to when you close it
  self.fullScreen = self.target ~= nil and self.target:isFullScreen() == true
  self.anchor = nil
  self:_showPanel()
  self:_send(hs.json.encode({ type = "note", title = "Your recurring fixes", text = "Loading…" }))
  self.insightsTask = hs.task.new(self.bin, function(_, stdout, stderr)
    local ok, data = pcall(hs.json.decode, stdout or "")
    if ok and type(data) == "table" then
      data.type = "insights"
      self:_send(hs.json.encode(data))
    else
      self:_send(hs.json.encode({ type = "note", title = "Your recurring fixes", text = stderr or "" }))
    end
  end, concat(self.args, { "insights", "--json" }))
  self.insightsTask:start()
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
  return self.panelFocused or (front ~= nil and front:bundleID() == HAMMERSPOON)
end

--- Penwise:quickFix()
--- Method
--- Fixes the selected text and replaces it right away, then says briefly what changed.
function obj:quickFix()
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
          hs.alert.show("Penwise: " .. summarize(applied) .. "  (⌘Z to undo)" .. note, 3)
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
  self:_log("hotkey in %s%s", (app and app:bundleID()) or "?", self.fullScreen and " (full screen)" or "")
  self:_readSelection(function(text)
    if not text or not text:find("%S") then
      hs.alert.show("Penwise: click in a text box, or select the text to check")
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

-- Where the text is on screen: the text field, or in a large one (a document), the selection.
local function textBounds(element)
  local frame = frameOf(element)
  if frame and frame.h <= 200 then return frame end
  return selectionBounds(element) or frame
end

-- Ask the app for its selected text. With nothing selected, use the whole text field if it
-- is short, or else the paragraph at the cursor. If the app can't say, copy with ⌘C.
-- `self.source` remembers where the text came from, so Replace can select it again; text that
-- can't be edited there (a terminal, a web page) is "readonly": the fix gets copied instead.
function obj:_readSelection(callback, lookedAgain)
  local element = attribute(hs.axuielement.systemWideElement(), "AXFocusedUIElement")
  local bundle = self.app and self.app:bundleID()
  local readonly = TERMINALS[bundle] or (element ~= nil and not editable(element))
  local function use(text, source, how)
    self.source = source
    self:_log("read: %s, %s%s, %d characters", how, tostring(element and attribute(element, "AXRole")),
      readonly and ", read-only" or "", #text)
    callback(text)
  end
  self.anchor = element and textBounds(element)
  if element then
    local selected = attribute(element, "AXSelectedText")
    if hasText(selected) then
      local range = attribute(element, "AXSelectedTextRange")
      return use(selected, { kind = readonly and "readonly" or "selection", element = element, range = range }, "selection")
    end
    local value = attribute(element, "AXValue")
    if not readonly and self.wholeFieldLimit > 0 and TEXT_FIELD_ROLES[attribute(element, "AXRole")] and hasText(value) then
      if #value <= self.wholeFieldLimit then
        self.anchor = frameOf(element) or self.anchor
        return use(value, { kind = "field", element = element }, "whole text box")
      end
      local paragraph, range = self:_paragraphAtCursor(element, value)
      if paragraph then
        self.anchor = selectionBounds(element, range) or self.anchor
        return use(paragraph, { kind = "paragraph", element = element, range = range }, "paragraph at the cursor")
      end
    end
  end
  if not lookedAgain and self.app and not hasText(element and attribute(element, "AXValue")) then
    -- Electron apps (Claude, Slack, Teams, ...) describe their text boxes to other apps only when
    -- asked to. Ask, give the app a moment, and look again.
    local ok, asked = pcall(function()
      return hs.axuielement.applicationElement(self.app):setAttributeValue("AXManualAccessibility", true)
    end)
    if ok and asked then
      self:_log("asked %s to describe its text boxes; looking again", tostring(bundle))
      self.lookAgainTimer = hs.timer.doAfter(0.3, function() self:_readSelection(callback, true) end)
      return
    end
  end

  local saved = hs.pasteboard.readAllData()
  local count = hs.pasteboard.changeCount()
  local started = hs.timer.secondsSinceEpoch()
  hs.eventtap.keyStroke({ "cmd" }, "c", 0)
  self.copyTimer = hs.timer.doEvery(0.02, function()
    local copied = hs.pasteboard.changeCount() ~= count
    if copied or hs.timer.secondsSinceEpoch() - started > 0.5 then
      self.copyTimer:stop()
      local text = copied and hs.pasteboard.getContents() or nil
      restoreClipboard(saved)
      self.source = { kind = readonly and "readonly" or "copy" }
      self:_log("read: copied with ⌘C, %d characters%s", text and #text or 0, readonly and ", read-only" or "")
      callback(text)
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

-- Where the panel goes: just above the text, below it when there is no room above, or
-- else in the middle of the screen.
local function placePanel(anchor, size, area)
  local gap = 8
  if anchor then
    local x = math.max(area.x + gap, math.min(anchor.x, area.x + area.w - size.w - gap))
    if anchor.y - gap - size.h >= area.y then
      return { x = x, y = anchor.y - gap - size.h }
    end
    if anchor.y + anchor.h + gap + size.h <= area.y + area.h then
      return { x = x, y = anchor.y + anchor.h + gap }
    end
  end
  return { x = area.x + (area.w - size.w) / 2, y = area.y + (area.h - size.h) / 3 }
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
          self:_returnToApp()
        elseif action == "focusChange" then
          self.panelFocused = hasFocus == true
          if not hasFocus and self.webview:isVisible() then
            self:_log("panel lost focus: closed")
            self:_close() -- you clicked somewhere else: get out of the way
          end
        end
      end)
      :html(self.html)
  end
  self:_placePanel()
  self.webview:show()
  if self.fullScreen then
    -- Bringing Hammerspoon forward would switch to the desktop: the panel takes the keyboard as it is.
    self:_log("panel shown over a full-screen app")
  else
    hs.focus()
    local window = self.webview:hswindow()
    if window then window:focus() end
    self:_log("panel shown")
  end
end

-- Size the panel to fit its content, and put it next to the text being checked. It is as
-- wide as the text field, within limits.
function obj:_placePanel()
  local screen = (self.target and self.target:screen()) or hs.screen.mainScreen()
  local area = screen:frame()
  local width = self.anchor and math.max(480, math.min(720, self.anchor.w)) or PANEL_WIDTH
  local size = { w = width, h = math.max(150, math.min(area.h * 0.7, self.panelHeight)) }
  local spot = placePanel(self.anchor, size, area)
  self.webview:frame({ x = spot.x, y = spot.y, w = size.w, h = size.h })
end

-- Check the text and stream the results into the review panel.
function obj:_review(text, mode)
  self.text, self.mode = text, mode
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
    self:_returnToApp()
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
    self:_close()
    self:_openInTerminal("doctor")
  elseif body.action == "cancel" then
    self:_close()
    self:_returnToApp()
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
  elseif text ~= self.text then
    self:_returnToApp(function() self:_pasteOver(text) end, function() self:_copyInstead(text) end)
  else
    self:_returnToApp()
  end
  if #changes > 0 then
    -- As an argument, like the text in _run: input written to stdin can be lost.
    local json = hs.json.encode({ changes = changes })
    self.recordTask = hs.task.new(self.bin, nil, concat(self.args, { "record", "--", json }))
    self.recordTask:start()
  end
end

function obj:_pasteOver(text)
  local function paste()
    local saved = hs.pasteboard.readAllData()
    hs.pasteboard.setContents(text)
    hs.eventtap.keyStroke({ "cmd" }, "v", 0)
    self.restoreTimer = hs.timer.doAfter(1, function() restoreClipboard(saved) end)
  end
  if self:_selectSource() then
    self:_log("selected the text, pasted the fix")
    return paste()
  end
  if self.source.kind ~= "field" then return self:_copyInstead(text) end
  -- Some apps only select through the keyboard.
  hs.eventtap.keyStroke({ "cmd" }, "a", 0)
  self.selectTimer = hs.timer.doAfter(0.1, function()
    local selected = attribute(self.source.element, "AXSelectedText")
    if selected == nil or sameText(selected, self.text) then
      self:_log("selected the text with ⌘A, pasted the fix")
      paste()
    else
      self:_copyInstead(text)
    end
  end)
end

function obj:_copyInstead(text)
  self:_log("couldn't select the text: copied the fix instead")
  hs.pasteboard.setContents(text)
  hs.alert.show("Penwise: couldn't select your text to replace it, so the fix is copied. Select your text and press ⌘V.", 6)
end

-- Select the text that was checked again. True when it is selected (or the app can't tell).
function obj:_selectSource()
  local source = self.source or {}
  local element = source.element
  if not element then return true end -- copied with ⌘C: the selection is still yours
  local ok, selected = pcall(function()
    if attribute(element, "AXFocused") == false then element:setAttributeValue("AXFocused", true) end
    if sameText(attribute(element, "AXSelectedText"), self.text) then return true end
    local range = source.range
    if source.kind == "field" then
      local value = attribute(element, "AXValue")
      range = { location = 0, length = utf16Length(type(value) == "string" and value or self.text) }
    end
    if type(range) == "table" then element:setAttributeValue("AXSelectedTextRange", range) end
    local now = attribute(element, "AXSelectedText")
    return now == nil or sameText(now, self.text)
  end)
  return ok and selected
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
  self.run = self.run + 1
  if self.task and self.task:isRunning() then self.task:terminate() end
  if self.webview then self.webview:hide() end
end

return obj
