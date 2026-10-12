-- A minimal stand-in for the Hammerspoon APIs the Penwise Spoon uses.
-- Tests set SPOON_DIR, SELECTION, run_command(path, args, input) and the JSON helpers.

LOG, JS = {}, {}
CLIPBOARD, COUNT = "user clipboard", 1

local function log(message) table.insert(LOG, message) end

local screen = { frame = function() return { x = 0, y = 0, w = 1440, h = 900 } end }
TARGET = { focus = function() log("focus target") end, screen = function() return screen end }

local webview = {}
for _, name in ipairs({ "windowStyle", "windowTitle", "allowTextEntry", "level", "windowCallback", "html", "show", "topLeft" }) do
  webview[name] = function(self) return self end
end
function webview:hide() log("hide panel"); return self end
function webview:frame() return { x = 0, y = 0, w = 640, h = 560 } end
function webview:hswindow() return { focus = function() end } end
function webview:isVisible() return false end
function webview:evaluateJavaScript(js) table.insert(JS, js) end

-- Tasks run when the test calls run_tasks(), standing in for Hammerspoon's event loop.
-- As in Hammerspoon, setInput() only queues the input: it is written from the event
-- loop, so stdin closed with closeInput() before then loses it.
TASKS = {}

local function newTask(path, done, stream, args)
  if type(stream) == "table" then args, stream = stream, nil end
  local task = { path = path, done = done, stream = stream, args = args }
  function task:start() table.insert(TASKS, self); return self end
  function task:isRunning() return false end
  function task:setInput(input) self.pending = input; return self end
  function task:closeInput() self.closed = true; return self end
  return task
end

function run_tasks()
  while #TASKS > 0 do
    local task = table.remove(TASKS, 1)
    local input = (not task.closed and task.pending) or ""
    local out, err, code = run_command(task.path, task.args, input)
    log("ran " .. table.concat(task.args, " "))
    if task.stream and DELIVERY == "stream" then
      -- Two chunks, split in the middle of a line, as a real pipe may do.
      local cut = math.floor(#out / 2)
      task.stream(task, out:sub(1, cut), "")
      task.stream(task, out:sub(cut + 1), "")
      if task.done then task.done(code, "", err) end
    elseif task.done then
      task.done(code, out, err)
    end
  end
end

hs = {
  logger = { new = function() return {} end },
  spoons = {
    scriptPath = function() return SPOON_DIR end,
    bindHotkeysToSpec = function(spec) HOTKEYS = spec end,
  },
  fs = { attributes = function() return {} end },
  alert = {
    show = function(message) log("alert " .. message); return message end,
    closeSpecific = function() end,
  },
  json = { encode = json_encode, decode = json_decode },
  window = { focusedWindow = function() return TARGET end },
  screen = { mainScreen = function() return screen end },
  uielement = {
    focusedElement = function() return { selectedText = function() return SELECTION end } end,
  },
  pasteboard = {
    readAllData = function() return { ["public.utf8-plain-text"] = CLIPBOARD } end,
    writeAllData = function(data) CLIPBOARD = data["public.utf8-plain-text"] end,
    setContents = function(text) CLIPBOARD = text; COUNT = COUNT + 1 end,
    getContents = function() return CLIPBOARD end,
    clearContents = function() CLIPBOARD = nil end,
    changeCount = function() return COUNT end,
  },
  eventtap = { keyStroke = function(_, key) log("cmd+" .. key .. ": " .. tostring(CLIPBOARD)) end },
  timer = { doAfter = function(_, fn) fn(); return {} end, secondsSinceEpoch = os.time },
  focus = function() end,
  drawing = { windowLevels = { floating = 3 } },
  webview = {
    new = function() return webview end,
    usercontent = { new = function() return { setCallback = function(_, fn) SEND_MESSAGE = fn end } end },
  },
  task = { new = newTask },
}
