import React from 'react'

var e = React.createElement;

function MetricCard(props) {
  var cls = 'stat-card';
  if (props.borderColor) cls += '';
  return e('div', { className: cls, style: props.borderColor ? { borderLeftColor: props.borderColor } : null },
    e('div', { className: 'stat-card__label' }, props.label),
    e('div', { className: 'stat-card__value' }, props.value),
    props.sub ? e('div', { className: 'stat-card__sub' }, props.sub) : null
  );
}

export { MetricCard }
