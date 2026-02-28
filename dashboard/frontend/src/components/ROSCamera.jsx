/**
 * ROSCamera — Live camera feed from ROS2 compressed image topic
 *
 * Props:
 *   ros    — ROSLIB.Ros instance
 *   topic  — string, e.g. '/camera/image/compressed'
 *   label  — display name, e.g. 'ZED Left'
 */
import React, { useState, useEffect, useRef } from 'react'
import ROSLIB from '../utils/roslib-browser.js'

var e = React.createElement

function ROSCamera(props) {
  var imageState = useState(null)
  var imageSrc = imageState[0]
  var setImageSrc = imageState[1]

  var hzState = useState(0)
  var hz = hzState[0]
  var setHz = hzState[1]

  var resState = useState('')
  var resolution = resState[0]
  var setResolution = resState[1]

  var staleState = useState(false)
  var isStale = staleState[0]
  var setIsStale = staleState[1]

  var frameCountRef = useRef(0)
  var lastHzRef = useRef(Date.now())
  var lastMsgRef = useRef(Date.now())

  useEffect(function () {
    if (!props.ros || !props.topic) return

    var topic = new ROSLIB.Topic({
      ros: props.ros,
      name: props.topic,
      messageType: 'sensor_msgs/CompressedImage'
    })

    topic.subscribe(function (msg) {
      lastMsgRef.current = Date.now()
      setIsStale(false)
      frameCountRef.current++

      // Update Hz counter every second
      var now = Date.now()
      if (now - lastHzRef.current >= 1000) {
        setHz(frameCountRef.current)
        frameCountRef.current = 0
        lastHzRef.current = now
      }

      // Render base64 image
      var format = msg.format || 'jpeg'
      setImageSrc('data:image/' + format + ';base64,' + msg.data)
    })

    // Staleness check
    var staleTimer = setInterval(function () {
      if (Date.now() - lastMsgRef.current > 2000) {
        setIsStale(true)
        setHz(0)
      }
    }, 1000)

    return function () {
      topic.unsubscribe()
      clearInterval(staleTimer)
    }
  }, [props.ros, props.topic])

  var containerStyle = {
    background: 'var(--surface)',
    border: '1px solid var(--border)',
    borderRadius: 'var(--radius)',
    overflow: 'hidden',
    position: 'relative'
  }

  var overlayStyle = {
    position: 'absolute', bottom: '0', left: '0', right: '0',
    background: 'linear-gradient(transparent, rgba(0,0,0,0.8))',
    padding: '8px 10px 6px',
    display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end',
    fontFamily: 'var(--font-mono)', fontSize: '10px', color: '#ccc'
  }

  return e('div', { style: containerStyle },
    imageSrc && !isStale
      ? e('img', {
          src: imageSrc,
          style: { width: '100%', height: 'auto', display: 'block' },
          alt: props.label || 'Camera feed'
        })
      : e('div', {
          style: {
            width: '100%', height: '180px', display: 'flex', alignItems: 'center',
            justifyContent: 'center', flexDirection: 'column', gap: '8px'
          }
        },
          isStale
            ? e('div', { style: { color: 'var(--warning)', fontSize: '12px', fontWeight: 600 } }, 'Reconnecting...')
            : e('div', { style: { color: 'var(--text-dim)', fontSize: '12px' } }, 'Awaiting camera feed...')
        ),

    // Overlay with topic info
    e('div', { style: overlayStyle },
      e('span', null, props.label || props.topic),
      e('span', null, hz + ' Hz'),
      resolution ? e('span', null, resolution) : null
    )
  )
}

export { ROSCamera }
