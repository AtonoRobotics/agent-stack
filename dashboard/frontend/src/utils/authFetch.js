function authFetch(url, options) {
  var token = localStorage.getItem('mc_token');
  if (!token) {
    localStorage.removeItem('mc_token');
    localStorage.removeItem('mc_user');
    window.location.reload();
    return Promise.reject(new Error('No token'));
  }
  var opts = Object.assign({}, options || {});
  opts.headers = Object.assign({
    'Authorization': 'Bearer ' + token,
    'Content-Type': 'application/json'
  }, opts.headers || {});
  return fetch(url, opts).then(function(r) {
    if (r.status === 401) {
      localStorage.removeItem('mc_token');
      localStorage.removeItem('mc_user');
      window.location.reload();
      return Promise.reject(new Error('Unauthorized'));
    }
    return r;
  });
}

export { authFetch }
