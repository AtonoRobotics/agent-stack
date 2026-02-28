import React from 'react'

var e = React.createElement;

function TabNav(props) {
  return e('div', { className: 'tab-nav' },
    props.tabs.map(function(t) {
      return e('div', {
        key: t,
        className: 'tab-nav__item' + (props.active === t ? ' tab-nav__item--active' : ''),
        onClick: function() { props.onChange(t); }
      }, t);
    })
  );
}

export { TabNav }
