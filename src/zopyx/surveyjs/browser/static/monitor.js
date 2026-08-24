/**
 * Survey Monitor Dashboard JavaScript
 * Handles chart rendering and auto-refresh functionality
 */

(function() {
  'use strict';

  // Configuration
  const REFRESH_INTERVAL = 30000; // 30 seconds
  let refreshTimer = null;
  let isRefreshing = false;

  // Initialize on DOM ready
  document.addEventListener('DOMContentLoaded', function() {
    initChart();
    initChartControls();
    initAutoRefresh();
    updateLastUpdated();
  });

  /**
   * Initialize the submission rate chart
   */
  function initChart() {
    const chartDataElement = document.getElementById('chart-data');
    if (!chartDataElement) return;

    try {
      const data = JSON.parse(chartDataElement.textContent);
      renderChart(data);
      renderLatencyChart(data);
    } catch (e) {
      console.error('Failed to parse chart data:', e);
    }
  }

  /**
   * Render the submission chart with Plotly.
   * Stacked per-form areas (submissions/min) + cumulative total line on a
   * secondary y-axis. The global per-minute series equals the stack sum.
   */
  const PALETTE = [
    '#3b82f6', '#10b981', '#f59e0b', '#ef4444',
    '#8b5cf6', '#ec4899', '#14b8a6', '#f97316',
    '#6366f1', '#84cc16',
  ];

  function renderChart(data) {
    const el = document.getElementById('submission-chart');
    if (!el) return;

    const hasData = data.labels &&
      data.labels.length > 0 &&
      (data.values || []).some(v => v > 0);
    if (!hasData) {
      el.innerHTML = '<div class="chart-empty">No data available for selected time window</div>';
      return;
    }

    const traces = [];
    (data.forms || []).forEach((form, i) => {
      traces.push({
        x: data.labels,
        y: form.values,
        name: form.title,
        type: 'scatter',
        mode: 'lines',
        stackgroup: 'one',
        line: { width: 0.5 },
        fillcolor: PALETTE[i % PALETTE.length],
        hovertemplate: '%{y} <b>' + form.title + '</b><extra></extra>',
      });
    });

    traces.push({
      x: data.labels,
      y: data.cumulative,
      name: 'Cumulative',
      type: 'scatter',
      mode: 'lines',
      yaxis: 'y2',
      line: { color: '#111827', width: 2.5 },
      hovertemplate: '%{y} total <extra>Cumulative</extra>',
    });

    const layout = {
      height: 400,
      margin: { t: 10, r: 65, b: 45, l: 45 },
      hovermode: 'x unified',
      legend: { orientation: 'h', y: -0.3, x: 0 },
      xaxis: { showgrid: false, tickangle: -45 },
      yaxis: { title: 'Submissions / min', rangemode: 'nonnegative', gridcolor: '#f3f4f6' },
      yaxis2: {
        title: 'Total',
        overlaying: 'y',
        side: 'right',
        showgrid: false,
        rangemode: 'nonnegative',
      },
    };

    // Preserve the user's zoom across auto-refresh redraws
    const prevRange = getXRange(el);
    Plotly.newPlot(el, traces, layout, {
      displayModeBar: false,
      responsive: true,
      scrollZoom: true,
    });
    if (prevRange) {
      Plotly.relayout(el, { 'xaxis.range': prevRange });
    }
  }

  /**
   * Render the processing-time chart with Plotly.
   * Average (solid) and max (dotted) server-side processing time per minute
   * in milliseconds; gaps where no submission was recorded.
   */
  function renderLatencyChart(data) {
    const el = document.getElementById('latency-chart');
    if (!el) return;

    const duration = data.duration || {};
    const avg = duration.avg || [];
    const maxVals = duration.max || [];
    const hasData = avg.some(v => v !== null && v !== undefined);
    if (!hasData) {
      el.innerHTML = '<div class="chart-empty">No data available for selected time window</div>';
      return;
    }

    const labels = data.labels || [];
    const prevRange = getXRange(el);
    Plotly.newPlot(el, [
      {
        x: labels,
        y: avg,
        name: 'Average',
        type: 'scatter',
        mode: 'lines',
        line: { color: '#3b82f6', width: 2 },
        hovertemplate: '%{y} ms <extra>Average</extra>',
      },
      {
        x: labels,
        y: maxVals,
        name: 'Max',
        type: 'scatter',
        mode: 'lines',
        line: { color: '#f59e0b', width: 1.5, dash: 'dot' },
        hovertemplate: '%{y} ms <extra>Max</extra>',
      },
    ], {
      height: 400,
      margin: { t: 10, r: 65, b: 45, l: 45 },
      hovermode: 'x unified',
      legend: { orientation: 'h', y: -0.3, x: 0 },
      xaxis: { showgrid: false, tickangle: -45 },
      yaxis: { title: 'ms', rangemode: 'nonnegative', gridcolor: '#f3f4f6' },
    }, {
      displayModeBar: false,
      responsive: true,
      scrollZoom: true,
    });
    if (prevRange) {
      Plotly.relayout(el, { 'xaxis.range': prevRange });
    }
  }

  /**
   * Current x-axis range of the chart, or null when fully autoranged.
   * Works for the categorical (HH:MM) axis: ranges are numeric indices.
   */
  function getXRange(el) {
    if (!el || !el.data || !el.data.length) return null;
    const layout = el.layout || {};
    if (layout.xaxis && Array.isArray(layout.xaxis.range)) return layout.xaxis.range;
    const full = (el._fullLayout && el._fullLayout.xaxis) || {};
    if (Array.isArray(full._range)) return full._range;
    if (Array.isArray(full.range)) return full.range;
    return null;
  }

  /** Zoom the chart by `factor` (< 1 zooms in, > 1 zooms out), keeping the
   *  center of the current view fixed. Clamped to the full data span. */
  function zoomChart(factor, chartId) {
    const el = document.getElementById(chartId);
    if (!el || !el.data || !el.data.length) return;
    const x = (el.data[0] && el.data[0].x) || [];
    const fullSpan = Math.max((x.length || 1) - 1, 1);
    // Autoranged chart has no stored range yet — start from the full span
    const range = getXRange(el) || [0, fullSpan];
    const center = (range[0] + range[1]) / 2;
    let halfSpan = ((range[1] - range[0]) / 2) * factor;
    halfSpan = Math.min(Math.max(halfSpan, 1), fullSpan);
    Plotly.relayout(el, { 'xaxis.range': [center - halfSpan, center + halfSpan] });
  }

  /** Reset the chart to the full time window. */
  function resetChart(chartId) {
    const el = document.getElementById(chartId);
    if (!el) return;
    Plotly.relayout(el, {
      'xaxis.autorange': true,
      'yaxis.autorange': true,
      'yaxis2.autorange': true,
    });
  }

  /** Wire up the zoom control buttons for both charts. */
  function initChartControls() {
    const bind = (btnId, fn) => {
      const btn = document.getElementById(btnId);
      if (btn) btn.addEventListener('click', fn);
    };
    bind('chart-zoom-in', () => zoomChart(0.5, 'submission-chart'));
    bind('chart-zoom-out', () => zoomChart(2, 'submission-chart'));
    bind('chart-reset', () => resetChart('submission-chart'));
    bind('latency-zoom-in', () => zoomChart(0.5, 'latency-chart'));
    bind('latency-zoom-out', () => zoomChart(2, 'latency-chart'));
    bind('latency-reset', () => resetChart('latency-chart'));
  }

  /**
   * Initialize auto-refresh functionality
   */
  function initAutoRefresh() {
    const checkbox = document.getElementById('auto-refresh');
    if (!checkbox) return;

    // Start auto-refresh
    startRefreshTimer();

    checkbox.addEventListener('change', function() {
      if (this.checked) {
        startRefreshTimer();
      } else {
        stopRefreshTimer();
      }
    });

    // Refresh on visibility change (when user returns to tab)
    document.addEventListener('visibilitychange', function() {
      if (document.hidden) {
        stopRefreshTimer();
      } else if (checkbox.checked) {
        refreshData();
        startRefreshTimer();
      }
    });
  }

  /**
   * Start the refresh timer
   */
  function startRefreshTimer() {
    stopRefreshTimer();
    refreshTimer = setInterval(refreshData, REFRESH_INTERVAL);
  }

  /**
   * Stop the refresh timer
   */
  function stopRefreshTimer() {
    if (refreshTimer) {
      clearInterval(refreshTimer);
      refreshTimer = null;
    }
  }

  /**
   * Refresh data via AJAX
   */
  function refreshData() {
    if (isRefreshing) return;
    isRefreshing = true;

    const windowValue = document.getElementById('current-window')?.textContent || '1h';
    const url = `@@survey-monitor?format=json&window=${encodeURIComponent(windowValue)}`;

    fetch(url, {
      method: 'GET',
      headers: {
        'Accept': 'application/json',
        'X-Requested-With': 'XMLHttpRequest'
      }
    })
    .then(response => {
      if (!response.ok) throw new Error('Network response was not ok');
      return response.json();
    })
    .then(data => {
      updateDashboard(data);
      updateLastUpdated();
    })
    .catch(error => {
      console.error('Refresh failed:', error);
    })
    .finally(() => {
      isRefreshing = false;
    });
  }

  /**
   * Update dashboard with new data
   */
  function updateDashboard(data) {
    if (data.error) {
      console.error('Dashboard error:', data.error);
      return;
    }

    // Update stat cards
    const totalCount = document.getElementById('total-count');
    const rateValue = document.getElementById('rate-value');
    const uniqueUsers = document.getElementById('unique-users');
    const activeForms = document.getElementById('active-forms');

    if (totalCount) totalCount.textContent = data.total_count || 0;
    if (rateValue) rateValue.textContent = data.rate_per_minute || 0;
    if (uniqueUsers) uniqueUsers.textContent = data.unique_users || 0;
    if (activeForms) activeForms.textContent = (data.forms || []).length;

    // Update rate limit status
    updateRateLimitStatus(data.rate_info);

    // Update chart
    if (data.time_series) {
      const labels = Object.keys(data.time_series);
      const values = Object.values(data.time_series);
      let running = 0;
      const cumulative = values.map(v => (running += v));
      const forms = (data.form_time_series || []).map(form => ({
        title: form.title || 'Untitled',
        values: labels.map(label => (form.series || {})[label] || 0),
      }));
      renderChart({ labels, values, cumulative, forms });
    }

    // Update latency chart
    if (data.duration_series) {
      const labels = Object.keys(data.time_series);
      const avg = [];
      const maxVals = [];
      labels.forEach(label => {
        const entry = data.duration_series[label];
        if (entry) {
          avg.push(Math.round((entry.avg || 0) * 1000));
          maxVals.push(Math.round((entry.max || 0) * 1000));
        } else {
          avg.push(null);
          maxVals.push(null);
        }
      });
      renderLatencyChart({ labels, duration: { avg, max: maxVals } });
    }

    // Update forms table (simplified - just refresh on next page load)
    // For a full update, we'd need to rebuild the table HTML
  }

  /**
   * Update rate limit status display
   */
  function updateRateLimitStatus(rateInfo) {
    if (!rateInfo) return;

    const currentEl = document.getElementById('rate-current');
    const avgEl = document.getElementById('rate-avg');
    const statusEl = document.getElementById('rate-status');

    if (currentEl) currentEl.textContent = rateInfo.current_minute_count || 0;
    if (avgEl) avgEl.textContent = rateInfo['5min_average'] || 0;

    if (statusEl) {
      if (rateInfo.is_allowed) {
        statusEl.className = 'rate-status rate-ok';
        statusEl.innerHTML = '✅ Within limits';
      } else {
        statusEl.className = 'rate-status rate-limited';
        statusEl.innerHTML = '⚠️ Rate limited';
      }
    }
  }

  /**
   * Update last updated timestamp
   */
  function updateLastUpdated() {
    const el = document.getElementById('last-updated');
    if (el) {
      const now = new Date();
      el.textContent = now.toLocaleTimeString();
    }
  }

  // Initialize sortable table
  function initSortableTable() {
    const table = document.getElementById('forms-table');
    if (!table) return;

    const headers = table.querySelectorAll('th.sortable');
    let currentSort = { column: null, direction: 'asc' };

    headers.forEach(header => {
      header.addEventListener('click', () => {
        const column = header.dataset.sort;
        
        // Toggle direction if same column
        if (currentSort.column === column) {
          currentSort.direction = currentSort.direction === 'asc' ? 'desc' : 'asc';
        } else {
          currentSort.column = column;
          currentSort.direction = 'desc'; // Default to desc for new column
        }

        // Update sort indicators
        headers.forEach(h => h.classList.remove('sort-asc', 'sort-desc'));
        header.classList.add(currentSort.direction === 'asc' ? 'sort-asc' : 'sort-desc');

        // Sort the table
        sortTable(table, column, currentSort.direction);
      });
    });
  }

  /**
   * Sort the forms table by a column
   */
  function sortTable(table, column, direction) {
    const tbody = table.querySelector('tbody');
    if (!tbody) return;

    const rows = Array.from(tbody.querySelectorAll('tr:not(.no-data-row)'));
    
    rows.sort((a, b) => {
      let aVal, bVal;

      if (column === 'title') {
        aVal = a.dataset.title || '';
        bVal = b.dataset.title || '';
        // String comparison for title
        return direction === 'asc'
          ? aVal.localeCompare(bVal)
          : bVal.localeCompare(aVal);
      } else if (column === 'avg_duration') {
        // Seconds stored in the data attribute -> compare as ms
        aVal = (parseFloat(a.dataset.avg_duration || '0') || 0) * 1000;
        bVal = (parseFloat(b.dataset.avg_duration || '0') || 0) * 1000;
        return direction === 'asc' ? aVal - bVal : bVal - aVal;
      } else {
        // Numeric comparison for count/unique_users
        aVal = parseInt(a.dataset[column] || 0, 10);
        bVal = parseInt(b.dataset[column] || 0, 10);
        return direction === 'asc' ? aVal - bVal : bVal - aVal;
      }
    });

    // Re-append rows in sorted order
    rows.forEach(row => tbody.appendChild(row));
  }

  // Initialize sortable table on DOM ready
  document.addEventListener('DOMContentLoaded', initSortableTable);

  // Expose refresh function globally for manual refresh
  window.refreshMonitor = refreshData;

})();
