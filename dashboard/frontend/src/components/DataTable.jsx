import React, { useState, useMemo } from 'react'

var e = React.createElement;

function DataTable(props) {
  var columns = props.columns;
  var data = props.data;
  var sortState = useState({ col: null, asc: true });
  var sortCol = sortState[0].col;
  var sortAsc = sortState[0].asc;
  var setSort = sortState[1];

  var sorted = useMemo(function() {
    if (!sortCol) return data;
    var copy = data.slice();
    copy.sort(function(a, b) {
      var va = a[sortCol], vb = b[sortCol];
      if (typeof va === 'number' && typeof vb === 'number') return sortAsc ? va - vb : vb - va;
      va = String(va); vb = String(vb);
      return sortAsc ? va.localeCompare(vb) : vb.localeCompare(va);
    });
    return copy;
  }, [data, sortCol, sortAsc]);

  function onSort(col) {
    setSort(function(prev) {
      if (prev.col === col) return { col: col, asc: !prev.asc };
      return { col: col, asc: true };
    });
  }

  return e('div', { style: { overflowX: 'auto' } },
    e('table', { className: 'data-table' },
      e('thead', null,
        e('tr', null,
          columns.map(function(c) {
            var arrow = sortCol === c.key ? (sortAsc ? ' \u25B2' : ' \u25BC') : '';
            return e('th', { key: c.key, onClick: function() { onSort(c.key); } },
              c.label, arrow ? e('span', { className: 'sort-arrow' }, arrow) : null
            );
          })
        )
      ),
      e('tbody', null,
        sorted.map(function(row, ri) {
          return e('tr', { key: ri },
            columns.map(function(c) {
              if (c.render) return e('td', { key: c.key }, c.render(row));
              var cls = c.mono ? 'mono' : '';
              return e('td', { key: c.key, className: cls }, row[c.key]);
            })
          );
        })
      )
    )
  );
}

export { DataTable }
