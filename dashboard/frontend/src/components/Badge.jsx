import React from 'react'

var e = React.createElement;

function Badge(props) {
  return e('span', { className: 'badge badge--' + (props.variant || 'neutral') }, props.children);
}

export { Badge }
