-- A minimal stand-in for the Hammerspoon APIs the Penwise Spoon uses.
-- Tests set SPOON_DIR, FIELD (the focused element's AX attributes), run_command(path, args,
-- input, env), ENVIRONMENT() (the environment a task starts with) and the JSON helpers. COPY_RESULT, if set, is what ⌘C puts on the clipboard, and
-- FIELD.BOUNDS where the selected text is on screen. PANEL holds the panel's window.
-- FIELD.IGNORES_AX_SELECTION makes the app ignore selections made through Accessibility, and
-- FIELD.IGNORES_SELECT_ALL makes it ignore ⌘A. HELD_KEYS is how many times the hotkey's
-- modifiers still read as held down. FIELD.COPY_ALL is what ⌘A then ⌘C copies. FRONT_APP is the app in front, when
-- it isn't the one being edited (APP_ID). FULL_SCREEN puts the app in full screen, FIELD.READONLY
-- makes the text not editable, and ELECTRON_FIELD is what an Electron app shows once asked to.

LOG, JS = {}, {}
CLIPBOARD, COUNT = "user clipboard", 1

local function log(message) table.insert(LOG, message) end

local screen = { frame = function() return { x = 0, y = 0, w = 1440, h = 900 } end }
TARGET = {
  focus = function() log("focus target") end,
  screen = function() return screen end,
  title = function() return WINDOW_TITLE or "Draft" end,
  isFullScreen = function() return FULL_SCREEN == true end,
  frame = function() return { x = 0, y = 0, w = 1440, h = 900 } end,
}

PANEL = { visible = false, frame = { x = 0, y = 0, w = 640, h = 560 } }
local webview = {}
for _, name in ipairs({ "transparent", "shadow", "windowTitle", "allowTextEntry", "level", "html" }) do
  webview[name] = function(self) return self end
end
function webview:behavior(value) PANEL.behavior = value; return self end
function webview:windowStyle(value) PANEL.style = value; return self end
function webview:windowCallback(fn) WINDOW_CALLBACK = fn; return self end
function webview:show() PANEL.visible = true; return self end
function webview:hide() log("hide panel"); PANEL.visible = false; return self end
function webview:isVisible() return PANEL.visible end
function webview:frame(rect)
  if rect then PANEL.frame = rect; return self end
  return PANEL.frame
end
function webview:hswindow() return { focus = function() end } end
function webview:evaluateJavaScript(js) table.insert(JS, js) end

-- Tasks run when the test calls run_tasks(), standing in for Hammerspoon's event loop.
-- Tasks get no stdin: Hammerspoon writes setInput() data later, from the event loop, and
-- it can be lost (with closeInput()) or never end (without), so the Spoon must not use it.
TASKS, TIMERS, DEFERRED = {}, {}, {}

function run_deferred()
  while #DEFERRED > 0 do table.remove(DEFERRED, 1)() end
end

local function newTask(path, done, stream, args)
  if type(stream) == "table" then args, stream = stream, nil end
  local task = { path = path, done = done, stream = stream, args = args }
  function task:start() table.insert(TASKS, self); return self end
  function task:isRunning() return false end
  function task:setInput() return self end
  function task:closeInput() return self end
  function task:environment() return ENVIRONMENT() end
  function task:setEnvironment(environment) self.env = environment; return self end
  return task
end

function run_tasks()
  while #TASKS > 0 or #TIMERS > 0 do
    while #TIMERS > 0 do
      local timer = table.remove(TIMERS, 1)
      for _ = 1, 100 do
        if not timer.running then break end
        timer.fn()
      end
    end
    if #TASKS == 0 then break end
    local task = table.remove(TASKS, 1)
    local out, err, code = run_command(task.path, task.args, "", task.env)
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

-- As in macOS, text ranges count UTF-16 units.
local function utf16sub(text, location, length)
  local out, units = {}, 0
  for _, code in utf8.codes(text) do
    if units >= location and units < location + length then table.insert(out, utf8.char(code)) end
    units = units + (code > 0xFFFF and 2 or 1)
  end
  return table.concat(out)
end

local field = {
  attributeValue = function(_, name)
    -- Like Chrome and Electron apps, report a new selection only a few reads later (SELECTION_LAG).
    if name == "AXSelectedText" and FIELD.PENDING_SELECTION then
      if (FIELD.SELECTION_LAG or 0) > 0 then
        FIELD.SELECTION_LAG = FIELD.SELECTION_LAG - 1
      else
        FIELD.AXSelectedText, FIELD.PENDING_SELECTION = FIELD.PENDING_SELECTION, nil
      end
    end
    return FIELD[name]
  end,
  setAttributeValue = function(self, name, value)
    if name == "AXSelectedTextRange" and FIELD.IGNORES_AX_SELECTION then return nil, "unsupported" end
    FIELD[name] = value
    if name == "AXSelectedTextRange" then
      FIELD.AXSelectedText = utf16sub(FIELD.AXValue, value.location, value.length)
    end
    return self
  end,
  parameterizedAttributeValue = function(_, name) return name == "AXBoundsForRange" and FIELD.BOUNDS or nil end,
  isAttributeSettable = function(_, name) return not (name == "AXValue" and FIELD.READONLY) end,
}

hs = {
  logger = { new = function() return {} end },
  spoons = {
    scriptPath = function() return SPOON_DIR end,
    bindHotkeysToSpec = function(spec, mapping) HOTKEYS, HOTKEY_KEYS = spec, mapping end,
  },
  fs = { attributes = function() return {} end },
  alert = {
    show = function(message) log("alert " .. message); return message end,
    closeSpecific = function() end,
  },
  json = { encode = json_encode, decode = json_decode },
  window = { focusedWindow = function() return TARGET end },
  application = {
    frontmostApplication = function()
      local id = FRONT_APP or APP_ID or "com.apple.TextEdit"
      return {
        bundleID = function() return id end,
        pid = function() return id == "org.hammerspoon.Hammerspoon" and 1 or 42 end,
        activate = function() end,
      }
    end,
  },
  screen = { mainScreen = function() return screen end },
  axuielement = {
    systemWideElement = function()
      -- FOCUS_LOST: nothing reports the focus. OTHER_FOCUS: the keyboard is in another element.
      local focused = field
      if OTHER_FOCUS then focused = { attributeValue = function(_, name) return OTHER_FOCUS[name] end } end
      return { attributeValue = function(_, name) return name == "AXFocusedUIElement" and not FOCUS_LOST and focused or nil end }
    end,
    applicationElement = function()
      return {
        setAttributeValue = function(self, name, value)
          log("app " .. name .. " = " .. tostring(value))
          if ELECTRON_FIELD then
            FIELD, ELECTRON_FIELD = ELECTRON_FIELD, nil
            return self
          end
        end,
      }
    end,
  },
  pasteboard = {
    readAllData = function() return { ["public.utf8-plain-text"] = CLIPBOARD } end,
    writeAllData = function(data) CLIPBOARD = data["public.utf8-plain-text"] end,
    setContents = function(text) CLIPBOARD = text; COUNT = COUNT + 1 end,
    getContents = function() return CLIPBOARD end,
    clearContents = function() CLIPBOARD = nil end,
    changeCount = function() return COUNT end,
  },
  eventtap = {
    keyStroke = function(mods, key)
      local cmd = mods[1] == "cmd"
      log(table.concat(mods, "+") .. "+" .. key .. ": " .. tostring(CLIPBOARD))
      if cmd and key == "c" and COPY_RESULT and (HELD_KEYS or 0) == 0 then
        CLIPBOARD, COUNT = COPY_RESULT, COUNT + 1
      elseif cmd and key == "c" and SELECTED_ALL and FIELD.COPY_ALL then
        CLIPBOARD, COUNT = FIELD.COPY_ALL, COUNT + 1 -- an app that only gives its text by copying
      elseif cmd and key == "a" and FIELD.COPY_ALL then
        SELECTED_ALL = true
      elseif cmd and key == "a" and not FIELD.IGNORES_SELECT_ALL then
        if FIELD.SELECTION_LAG then FIELD.PENDING_SELECTION = FIELD.AXValue else FIELD.AXSelectedText = FIELD.AXValue end
      elseif cmd and key == "v" and FIELD.AXValue and FIELD.AXSelectedText and FIELD.AXSelectedText ~= "" then
        -- The paste replaces the selection; PASTE_LOSES_LAST: an app that drops the last character.
        local pasted = FIELD.PASTE_LOSES_LAST and CLIPBOARD:sub(1, -2) or CLIPBOARD
        local first, last = FIELD.AXValue:find(FIELD.AXSelectedText, 1, true)
        if first then FIELD.AXValue = FIELD.AXValue:sub(1, first - 1) .. pasted .. FIELD.AXValue:sub(last + 1) end
        FIELD.AXSelectedText = ""
      end
    end,
    -- A click in a text box gives it the keyboard back.
    leftClick = function(point)
      log(string.format("click %d,%d", point.x, point.y))
      OTHER_FOCUS = nil
    end,
    checkKeyboardModifiers = function()
      KEY_CHECKS = (KEY_CHECKS or 0) + 1
      if (HELD_KEYS or 0) > 0 then
        HELD_KEYS = HELD_KEYS - 1
        return { ctrl = true, alt = true }
      end
      return {}
    end,
  },
  timer = {
    -- One-off timers fire at once, or, with DEFER_AFTER, when the test calls run_deferred().
    doAfter = function(_, fn)
      if DEFER_AFTER then table.insert(DEFERRED, fn) else fn() end
      return {}
    end,
    -- Like Hammerspoon, repeating timers fire later, from the event loop (run_tasks).
    -- Long ones (like the daily update check) never fire in tests.
    doEvery = function(interval, fn)
      local timer = { fn = fn, running = true }
      function timer:stop() self.running = false end
      if interval < 60 then table.insert(TIMERS, timer) end
      return timer
    end,
    secondsSinceEpoch = function() CLOCK = (CLOCK or 0) + 0.1; return CLOCK end,
  },
  focus = function() log("activate Hammerspoon") end,
  accessibilityState = function() return ACCESSIBILITY ~= false end,
  autoLaunch = function(on) log("hammerspoon starts at login: " .. tostring(on)) end,
  menuIcon = function(on) log("hammerspoon menu icon: " .. tostring(on)) end,
  dockIcon = function(on) log("hammerspoon dock icon: " .. tostring(on)) end,
  closePreferences = function() log("close hammerspoon preferences") end,
  drawing = { windowLevels = { floating = 3 }, windowBehaviors = { canJoinAllSpaces = 1, fullScreenAuxiliary = 256 } },
  webview = {
    windowMasks = { borderless = 0, nonactivating = 128 },
    new = function() return webview end,
    usercontent = { new = function() return { setCallback = function(_, fn) SEND_MESSAGE = fn end } end },
  },
  task = { new = newTask },
  menubar = {
    new = function()
      local menu = {}
      function menu:setTitle(title) MENU_TITLE = title; return self end
      function menu:setTooltip() return self end
      function menu:setMenu(fn) MENU = fn; return self end
      function menu:delete() MENU = nil end
      return menu
    end,
  },
  mouse = {
    absolutePosition = function(point)
      if point then MOUSE = point end
      return MOUSE
    end,
  },
  urlevent = { openURL = function(url) log("open " .. url) end },
  -- Hammerspoon's own store, kept across restarts.
  settings = {
    get = function(key) return (SETTINGS_STORE or {})[key] end,
    set = function(key, value) SETTINGS_STORE = SETTINGS_STORE or {}; SETTINGS_STORE[key] = value end,
  },
  osascript = { applescript = function(script) log("applescript " .. script); return true end },
}
