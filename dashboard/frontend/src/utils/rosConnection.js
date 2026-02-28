/**
 * ROS Connection Manager — singleton for rosbridge WebSocket
 *
 * Provides a shared ROSLIB.Ros instance with auto-reconnect,
 * connection status tracking, and topic subscription helpers.
 */
import ROSLIB from './roslib-browser.js'

var _instance = null
var _listeners = []
var _status = 'disconnected' // 'connected' | 'disconnected' | 'error'
var _reconnectTimer = null
var _reconnectDelay = 3000
var _maxReconnectDelay = 30000

function getDefaultUrl() {
  var host = location.hostname || 'localhost'
  return 'ws://' + host + ':9090'
}

function notifyListeners() {
  for (var i = 0; i < _listeners.length; i++) {
    try { _listeners[i](_status) } catch (ex) { /* ignore */ }
  }
}

function createRos(url) {
  if (_instance) {
    try { _instance.close() } catch (ex) { /* ignore */ }
  }
  if (_reconnectTimer) {
    clearTimeout(_reconnectTimer)
    _reconnectTimer = null
  }

  var ros = new ROSLIB.Ros()

  ros.on('connection', function () {
    _status = 'connected'
    _reconnectDelay = 3000
    notifyListeners()
  })

  ros.on('error', function () {
    _status = 'error'
    notifyListeners()
  })

  ros.on('close', function () {
    _status = 'disconnected'
    notifyListeners()
    // Auto-reconnect with exponential backoff
    _reconnectTimer = setTimeout(function () {
      if (_instance === ros) {
        try { ros.connect(url || getDefaultUrl()) } catch (ex) { /* ignore */ }
      }
    }, _reconnectDelay)
    _reconnectDelay = Math.min(_reconnectDelay * 1.5, _maxReconnectDelay)
  })

  _instance = ros

  try {
    ros.connect(url || getDefaultUrl())
  } catch (ex) {
    _status = 'error'
    notifyListeners()
  }

  return ros
}

/** Get or create the singleton ROSLIB.Ros instance */
function getRos(url) {
  if (!_instance) {
    createRos(url)
  }
  return _instance
}

/** Get current connection status */
function getStatus() {
  return _status
}

/** Subscribe to status changes. Returns unsubscribe function. */
function onStatusChange(fn) {
  _listeners.push(fn)
  return function () {
    _listeners = _listeners.filter(function (f) { return f !== fn })
  }
}

/** Disconnect and clean up */
function disconnect() {
  if (_reconnectTimer) {
    clearTimeout(_reconnectTimer)
    _reconnectTimer = null
  }
  if (_instance) {
    try { _instance.close() } catch (ex) { /* ignore */ }
    _instance = null
  }
  _status = 'disconnected'
  notifyListeners()
}

/** Reconnect (e.g. after manual disconnect or URL change) */
function reconnect(url) {
  disconnect()
  createRos(url)
}

/** Create a TFClient for the given fixed frame */
function createTFClient(ros, fixedFrame) {
  return new ROSLIB.TFClient({
    ros: ros,
    fixedFrame: fixedFrame || 'base_link',
    angularThres: 0.01,
    transThres: 0.01,
    rate: 10.0
  })
}

/** Subscribe to a ROS topic. Returns the Topic object (call .unsubscribe() to stop). */
function subscribeTopic(ros, topicName, messageType, callback) {
  var topic = new ROSLIB.Topic({
    ros: ros,
    name: topicName,
    messageType: messageType
  })
  topic.subscribe(callback)
  return topic
}

export {
  getRos,
  getStatus,
  onStatusChange,
  disconnect,
  reconnect,
  createTFClient,
  subscribeTopic,
  getDefaultUrl,
  ROSLIB
}
