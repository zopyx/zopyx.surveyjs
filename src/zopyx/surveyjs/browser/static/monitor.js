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
    } catch (e) {
      console.error('Failed to parse chart data:', e);
    }
  }

  /**
   * Render an SVG area chart
   * Shows full time window but only plots data between first and last events
   */
  function renderChart(data) {
    const svg = document.getElementById('submission-chart');
    const chartArea = svg.querySelector('#chart-area');
    
    if (!chartArea || !data.labels || !data.values || data.values.length === 0) {
      // Render empty state
      renderEmptyChart(chartArea);
      return;
    }

    const labels = data.labels;
    const values = data.values;
    const maxValue = Math.max(...values, 1);
    
    // Find first and last non-zero indices (event range)
    let firstEventIdx = values.findIndex(v => v > 0);
    let lastEventIdx = values.length - 1;
    for (let i = values.length - 1; i >= 0; i--) {
      if (values[i] > 0) {
        lastEventIdx = i;
        break;
      }
    }
    
    // If no events, show empty chart
    if (firstEventIdx === -1) {
      renderEmptyChart(chartArea);
      return;
    }
    
    // Chart dimensions
    const width = 800;
    const height = 200;
    const padding = { top: 20, right: 20, bottom: 40, left: 50 };
    const chartWidth = width - padding.left - padding.right;
    const chartHeight = height - padding.top - padding.bottom;

    // Clear existing
    chartArea.innerHTML = '';

    // Create scales
    const xScale = (i) => padding.left + (i / (values.length - 1 || 1)) * chartWidth;
    const yScale = (v) => padding.top + chartHeight - (v / maxValue) * chartHeight;

    // Add grid lines
    const gridGroup = document.createElementNS('http://www.w3.org/2000/svg', 'g');
    for (let i = 0; i <= 5; i++) {
      const y = padding.top + (chartHeight * i) / 5;
      const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
      line.setAttribute('x1', padding.left);
      line.setAttribute('y1', y);
      line.setAttribute('x2', width - padding.right);
      line.setAttribute('y2', y);
      line.setAttribute('class', 'chart-grid');
      gridGroup.appendChild(line);

      // Y-axis labels
      const text = document.createElementNS('http://www.w3.org/2000/svg', 'text');
      text.setAttribute('x', padding.left - 10);
      text.setAttribute('y', y + 4);
      text.setAttribute('text-anchor', 'end');
      text.setAttribute('font-size', '11');
      text.setAttribute('fill', '#9ca3af');
      text.textContent = Math.round(maxValue * (5 - i) / 5);
      gridGroup.appendChild(text);
    }
    chartArea.appendChild(gridGroup);

    // Create area path - only between first and last event
    let areaPath = `M ${xScale(firstEventIdx)} ${padding.top + chartHeight}`;
    for (let i = firstEventIdx; i <= lastEventIdx; i++) {
      areaPath += ` L ${xScale(i)} ${yScale(values[i])}`;
    }
    areaPath += ` L ${xScale(lastEventIdx)} ${padding.top + chartHeight} Z`;

    const area = document.createElementNS('http://www.w3.org/2000/svg', 'path');
    area.setAttribute('d', areaPath);
    area.setAttribute('class', 'chart-area');
    chartArea.appendChild(area);

    // Create line path - only between first and last event
    let linePath = `M ${xScale(firstEventIdx)} ${yScale(values[firstEventIdx])}`;
    for (let i = firstEventIdx + 1; i <= lastEventIdx; i++) {
      linePath += ` L ${xScale(i)} ${yScale(values[i])}`;
    }

    const line = document.createElementNS('http://www.w3.org/2000/svg', 'path');
    line.setAttribute('d', linePath);
    line.setAttribute('class', 'chart-line');
    chartArea.appendChild(line);

    // Add data points - only between first and last event
    for (let i = firstEventIdx; i <= lastEventIdx; i++) {
      const dot = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
      dot.setAttribute('cx', xScale(i));
      dot.setAttribute('cy', yScale(values[i]));
      dot.setAttribute('r', values[i] > 0 ? 4 : 2);
      dot.setAttribute('class', 'chart-dot');
      dot.setAttribute('title', `${labels[i]}: ${values[i]} submissions`);
      if (values[i] === 0) {
        dot.setAttribute('opacity', '0.3');
      }
      chartArea.appendChild(dot);
    }

    // X-axis labels (show subset if many) - show full range
    const labelStep = Math.ceil(labels.length / 8);
    labels.forEach((label, i) => {
      if (i % labelStep === 0 || i === labels.length - 1 || i === 0) {
        const text = document.createElementNS('http://www.w3.org/2000/svg', 'text');
        text.setAttribute('x', xScale(i));
        text.setAttribute('y', height - 10);
        text.setAttribute('text-anchor', 'middle');
        text.setAttribute('font-size', '11');
        text.setAttribute('fill', '#9ca3af');
        text.setAttribute('transform', `rotate(-45, ${xScale(i)}, ${height - 10})`);
        text.textContent = label;
        chartArea.appendChild(text);
      }
    });
  }

  /**
   * Render empty chart state
   */
  function renderEmptyChart(chartArea) {
    if (!chartArea) return;
    chartArea.innerHTML = '';

    const text = document.createElementNS('http://www.w3.org/2000/svg', 'text');
    text.setAttribute('x', '400');
    text.setAttribute('y', '100');
    text.setAttribute('text-anchor', 'middle');
    text.setAttribute('font-size', '14');
    text.setAttribute('fill', '#9ca3af');
    text.textContent = 'No data available for selected time window';
    chartArea.appendChild(text);
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
      const chartData = {
        labels: Object.keys(data.time_series),
        values: Object.values(data.time_series)
      };
      renderChart(chartData);
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
