import React from 'react'
import { NavContext } from '../contexts/NavContext'
import { Icon } from './Icon'

var e = React.createElement;

function MobileNav() {
  var nav = React.useContext(NavContext);
  var currentPage = nav.page;
  var links = [
    { page: 'lab', icon: 'home', label: 'Control' },
    { page: 'robot', icon: 'robot', label: 'Robots' , params: { id: 'dobot_cr10' } },
    { page: 'fleet', icon: 'server', label: 'Fleet' },
    { page: 'simulations', icon: 'play', label: 'Sims' },
    { page: 'demos', icon: 'activity', label: 'Demos' },
    { page: 'training', icon: 'brain', label: 'Training' },
    { page: 'agents', icon: 'users', label: 'Agents' }
  ];
  return e('nav', { className: 'mobile-nav' },
    links.map(function(l) {
      return e('a', {
        key: l.page, href: '#',
        className: 'mobile-nav__link' + (currentPage === l.page ? ' mobile-nav__link--active' : ''),
        onClick: function(ev) { ev.preventDefault(); nav.navigate(l.page, l.params); }
      }, Icon(l.icon), e('span', null, l.label));
    })
  );
}

export { MobileNav }
