import React from 'react'

var e = React.createElement;

function ProgressBar(props) {
  var pct = props.value || 0;
  return e('div', { className: 'progress-bar' },
    e('div', { className: 'progress-bar__track' },
      e('div', { className: 'progress-bar__fill', style: { width: pct + '%' } })
    ),
    e('span', { className: 'progress-bar__label' }, pct + '%')
  );
}

export { ProgressBar }
