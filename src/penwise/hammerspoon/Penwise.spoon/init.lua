--- === Penwise ===
---
--- Select text in any app, press a hotkey, and review suggested English fixes,
--- each with a short note. Press Return to replace your selection.
---
--- Requires the `penwise` command: https://github.com/LuckyLetter/penwise

local obj = {}
obj.__index = obj

obj.name = "Penwise"
obj.version = "0.3.0"
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
--- a comment, a form field) is checked as a whole. Set to 0 to always require a selection.
obj.wholeFieldLimit = 2000

--- Penwise.showMenu
--- Variable
--- Show the Penwise icon in the menu bar (when `start()` is called).
obj.showMenu = true

--- Penwise.checkForUpdates
--- Variable
--- Look for a new version once a day; when there is one, the menu offers to update.
obj.checkForUpdates = true

obj.logger = hs.logger.new("Penwise")

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
    action("Check selection", "fix", function() self:check("fix") end),
    action("Improve selection", "improve", function() self:check("improve") end),
    action("Quick fix selection", "quick", function() self:quickFix() end),
    { title = "-" },
    { title = "Your recurring fixes…", fn = function() self:showInsights() end },
    { title = "Change model or API key…", fn = function() self:_openInTerminal("setup") end },
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
  if self.webview and self.webview:isVisible() then
    self:_review(self.text, mode)
    return
  end
  self:_withSelection(function(text)
    self:_showPanel()
    self:_review(text, mode)
  end)
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
  self.target = hs.window.focusedWindow()
  local app = hs.application.frontmostApplication()
  -- Where the text is going (an email, a chat) sets the tone of "improve".
  self.context = {
    "--app", (app and app:bundleID()) or "",
    "--window", (self.target and self.target:title()) or "",
  }
  self:_readSelection(function(text)
    if not text or not text:find("%S") then
      hs.alert.show("Penwise: select some text first")
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

-- Ask the app for its selected text. With nothing selected in a short text field, select
-- and use the whole field. If the app can't say, copy the selection with ⌘C.
function obj:_readSelection(callback)
  local element = attribute(hs.axuielement.systemWideElement(), "AXFocusedUIElement")
  if element then
    local selected = attribute(element, "AXSelectedText")
    if type(selected) == "string" and selected:find("%S") then
      callback(selected)
      return
    end
    local value = attribute(element, "AXValue")
    if TEXT_FIELD_ROLES[attribute(element, "AXRole")] and type(value) == "string" and value:find("%S")
      and #value <= self.wholeFieldLimit then
      hs.eventtap.keyStroke({ "cmd" }, "a", 0)
      callback(value)
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
      callback(text)
    end
  end)
end

function obj:_showPanel()
  if not self.webview then
    local content = hs.webview.usercontent.new("penwise")
    content:setCallback(function(message) self:_onMessage(message.body) end)
    self.ready = false
    self.webview = hs.webview.new({ x = 0, y = 0, w = 640, h = 560 }, {}, content)
      :windowStyle({ "titled", "closable", "resizable" })
      :windowTitle("Penwise")
      :allowTextEntry(true)
      :level(hs.drawing.windowLevels.floating)
      :windowCallback(function(action)
        if action == "closing" then self:_close(true) end
      end)
      :html(self.html)
  end
  local screen = (self.target and self.target:screen()) or hs.screen.mainScreen()
  local area = screen:frame()
  local size = self.webview:frame()
  self.webview:topLeft({ x = area.x + (area.w - size.w) / 2, y = area.y + (area.h - size.h) / 3 })
  self.webview:show()
  hs.focus()
  local window = self.webview:hswindow()
  if window then window:focus() end
end

-- Check the text and stream the results into the review panel.
function obj:_review(text, mode)
  self.text, self.mode = text, mode
  self:_send(hs.json.encode({ type = "begin", original = text, mode = mode }))
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
  elseif body.action == "replace" then
    self:_replace(body.text, body.changes or {})
  elseif body.action == "copy" then
    hs.pasteboard.setContents(body.text)
    self:_close(true)
    hs.alert.show("Copied")
  elseif body.action == "mode" then
    self:_review(self.text, body.mode)
  elseif body.action == "keep" then
    self.keepTask = hs.task.new(self.bin, nil, concat(self.args, { "keep", "--", body.word }))
    self.keepTask:start()
  elseif body.action == "doctor" then
    self:_close(false)
    self:_openInTerminal("doctor")
  elseif body.action == "cancel" then
    self:_close(true)
  end
end

-- Paste the accepted text over the original selection, then put the clipboard back.
function obj:_replace(text, changes)
  self:_close(true)
  if text ~= self.text then
    self.pasteTimer = hs.timer.doAfter(0.15, function()
      local saved = hs.pasteboard.readAllData()
      hs.pasteboard.setContents(text)
      hs.eventtap.keyStroke({ "cmd" }, "v", 0)
      self.restoreTimer = hs.timer.doAfter(0.5, function() restoreClipboard(saved) end)
    end)
  end
  if #changes > 0 then
    self.recordTask = hs.task.new(self.bin, nil, concat(self.args, { "record" }))
    self.recordTask:setInput(hs.json.encode({ changes = changes }))
    self.recordTask:start()
  end
end

function obj:_close(refocus)
  self.run = self.run + 1 -- ignore output from a check that is still running
  if self.task and self.task:isRunning() then self.task:terminate() end
  if self.webview then self.webview:hide() end
  if refocus and self.target then self.target:focus() end
end

return obj
