function parseCSV(text) {
  var lines = text.trim().split('\n');
  var headers = lines[0].split(',').map(function(h) { return h.trim(); });
  var data = [];
  for (var i = 1; i < lines.length; i++) {
    if (!lines[i].trim()) continue;
    var vals = lines[i].split(',').map(parseFloat);
    var row = {};
    headers.forEach(function(h, j) { row[h] = vals[j]; });
    data.push(row);
  }
  return { headers: headers, data: data };
}

function computeVelocity(data, posKey, timeKey) {
  var result = [];
  for (var i = 0; i < data.length; i++) {
    var dt, dq;
    if (i === 0) { dt = data[1][timeKey] - data[0][timeKey]; dq = data[1][posKey] - data[0][posKey]; }
    else if (i === data.length - 1) { dt = data[i][timeKey] - data[i-1][timeKey]; dq = data[i][posKey] - data[i-1][posKey]; }
    else { dt = data[i+1][timeKey] - data[i-1][timeKey]; dq = data[i+1][posKey] - data[i-1][posKey]; }
    result.push(dt > 0 ? dq / dt : 0);
  }
  return result;
}

export { parseCSV, computeVelocity }
