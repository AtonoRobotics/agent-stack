import React, { useState } from 'react'

var e = React.createElement;

function LoginPage(props) {
  var usernameState = useState('');
  var username = usernameState[0];
  var setUsername = usernameState[1];
  var passwordState = useState('');
  var password = passwordState[0];
  var setPassword = passwordState[1];
  var errorState = useState('');
  var error = errorState[0];
  var setError = errorState[1];
  var loadingState = useState(false);
  var loading = loadingState[0];
  var setLoading = loadingState[1];

  function handleSubmit(ev) {
    ev.preventDefault();
    if (!username || !password) return;
    setLoading(true);
    setError('');
    fetch('/api/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username: username, password: password })
    })
    .then(function(r) {
      if (!r.ok) return r.json().then(function(d) { throw new Error(d.detail || 'Login failed'); });
      return r.json();
    })
    .then(function(data) {
      localStorage.setItem('mc_token', data.token);
      localStorage.setItem('mc_user', JSON.stringify({ username: data.username, role: data.role }));
      props.onLogin({ username: data.username, role: data.role }, data.token);
    })
    .catch(function(err) {
      setError(err.message || 'Login failed');
      setLoading(false);
    });
  }

  return e('div', { className: 'login-page' },
    e('form', { className: 'login-card', onSubmit: handleSubmit },
      e('div', { className: 'login-card__logo' },
        e('div', { className: 'login-card__logo-symbol' }, '\u03B1'),
        e('div', { className: 'login-card__logo-name' }, 'MISSION CONTROL'),
        e('div', { className: 'login-card__logo-company' }, 'by Alpha'),
        e('div', { className: 'login-card__divider' })
      ),
      error ? e('div', { className: 'login-error' }, error) : null,
      e('div', { className: 'login-field' },
        e('label', null, 'Username'),
        e('input', {
          type: 'text', value: username, autoFocus: true, autoComplete: 'username',
          onChange: function(ev) { setUsername(ev.target.value); }
        })
      ),
      e('div', { className: 'login-field' },
        e('label', null, 'Password'),
        e('input', {
          type: 'password', value: password, autoComplete: 'current-password',
          onChange: function(ev) { setPassword(ev.target.value); }
        })
      ),
      e('button', { className: 'login-btn', type: 'submit', disabled: loading },
        loading ? 'Authenticating...' : 'AUTHENTICATE'
      ),
      e('div', { className: 'login-footer' },
        e('div', null, 'Mission Control v1.0'),
        e('div', { style: { marginTop: '2px' } }, '\u00A9 2026 Alpha. Proprietary Software.')
      )
    )
  );
}

export { LoginPage }
