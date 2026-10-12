--- === Penwise ===
---
--- Select text in any app, press a hotkey, and review suggested English fixes,
--- each with a short note. Press Return to replace your selection.
---
--- Requires the `penwise` command: https://github.com/LuckyLetter/penwise

local obj = {}
obj.__index = obj

obj.name = "Penwise"
obj.version = "0.1.0"
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

function obj:init()
  self.html = readFile(spoonPath .. "panel.html")
  self.run = 0
  self.queue = {}
  return self
end

--- Penwise:bindHotkeys(mapping)
--- Method
--- Binds hotkeys. Keys of `mapping`: `fix` (only errors) and `improve` (also clarity and flow).
function obj:bindHotkeys(mapping)
  hs.spoons.bindHotkeysToSpec({
    fix = function() self:check("fix") end,
    improve = function() self:check("improve") end,
  }, mapping)
  return self
end

--- Penwise:check(mode)
--- Method
--- Reads the selected text in the frontmost app and opens the review panel.
function obj:check(mode)
  if self.webview and self.webview:isVisible() then
    self:_start(self.text, mode)
    return
  end
  if not hs.fs.attributes(self.bin) then
    hs.alert.show("Penwise: command not found at " .. self.bin .. ". Run `penwise setup-mac` again.")
    return
  end
  self.target = hs.window.focusedWindow()
  self:_readSelection(function(text)
    if not text or not text:find("%S") then
      hs.alert.show("Penwise: select some text first")
      return
    end
    self:_showPanel()
    self:_start(text, mode)
  end)
end

-- Ask the app for its selected text; if it can't say, copy it with ⌘C.
function obj:_readSelection(callback)
  local element = hs.uielement.focusedElement()
  if element and element.selectedText then
    local ok, text = pcall(function() return element:selectedText() end)
    if ok and text and text:find("%S") then
      callback(text)
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

-- Run `penwise check` and stream its events into the panel.
function obj:_start(text, mode)
  self.run = self.run + 1
  local run = self.run
  if self.task and self.task:isRunning() then self.task:terminate() end
  self.text, self.mode = text, mode
  self:_send(hs.json.encode({ type = "begin", original = text, mode = mode }))

  local buffer, seen, finished = "", {}, false
  local function forward(lines)
    for _, line in ipairs(lines) do
      local ok, event = pcall(hs.json.decode, line)
      if not seen[line] and ok and type(event) == "table" then
        seen[line] = true
        finished = finished or event.type == "done" or event.type == "error"
        self:_send(line)
      end
    end
  end

  local args = concat(self.args, { "check", "--format", "jsonl", "--mode", mode })
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
      self:_send(hs.json.encode({ type = "error", message = message }))
    end
  end, function(_, stdout)
    if run ~= self.run then return false end
    local lines
    lines, buffer = takeLines(buffer .. (stdout or ""))
    forward(lines)
    return true
  end, args)

  self.task:start()
  self.task:setInput(text)
  self.task:closeInput()
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
    self:_start(self.text, body.mode)
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
