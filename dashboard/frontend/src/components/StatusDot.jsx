import React from 'react'

var e = React.createElement;

function StatusDot(props) {
  var s = props.status || 'online';
  var cls = 'status-dot status-dot--' + s;
  if (props.large) cls += ' status-dot--lg';
  return e('span', { className: cls });
}

export { StatusDot }
