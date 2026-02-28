import { useState, useEffect, useRef } from 'react'

function useWebSocket() {
  var wsState = useState('disconnected');
  var wsStatus = wsState[0];
  var setWsStatus = wsState[1];
  var wsRef = useRef(null);
  var reconnectRef = useRef(null);

  useEffect(function() {
    function connect() {
      try {
        var protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
        var wsToken = localStorage.getItem('mc_token') || '';
        var ws = new WebSocket(protocol + '//' + location.host + '/ws/live?token=' + encodeURIComponent(wsToken));
        wsRef.current = ws;
        ws.onopen = function() { setWsStatus('connected'); };
        ws.onclose = function() {
          setWsStatus('disconnected');
          reconnectRef.current = setTimeout(connect, 3000);
        };
        ws.onerror = function() { setWsStatus('error'); };
        ws.onmessage = function(evt) {
          try { /* handle incoming messages */ } catch(e) {}
        };
      } catch(err) {
        setWsStatus('error');
        reconnectRef.current = setTimeout(connect, 5000);
      }
    }
    connect();
    return function() {
      if (wsRef.current) wsRef.current.close();
      if (reconnectRef.current) clearTimeout(reconnectRef.current);
    };
  }, []);

  return wsStatus;
}

export { useWebSocket }
