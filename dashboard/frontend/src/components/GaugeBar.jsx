import React from 'react'

var e = React.createElement;

function GaugeBar(props) {
  var pct = props.value || 0;
  var color = pct > 85 ? 'red' : pct > 60 ? 'amber' : 'green';
  if (props.color) color = props.color;
  return e('div', { className: 'gauge' },
    e('div', { className: 'gauge__header' },
      e('span', { className: 'gauge__label' }, props.label),
      e('span', { className: 'gauge__value' }, pct + '%' + (props.detail ? ' | ' + props.detail : ''))
    ),
    e('div', { className: 'gauge__track' },
      e('div', { className: 'gauge__fill gauge__fill--' + color, style: { width: pct + '%' } })
    )
  );
}

export { GaugeBar }
