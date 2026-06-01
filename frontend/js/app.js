// ── API helper ────────────────────────────────────────────────────────────────

async function api(path, opts = {}) {
  const res = await fetch('/api/v1' + path, opts);
  if (!res.ok) throw new Error(`API ${path} → ${res.status}`);
  return res.json();
}

// ── Global filter state ───────────────────────────────────────────────────────

const filters = {
  from_dt: null,
  to_dt: null,
  employee_id: null,
  classification: null,
};

// ── Router ────────────────────────────────────────────────────────────────────

const routes = {
  dashboard: loadDashboard,
  timeline: loadTimeline,
  log: loadLog,
  reports: loadReports,
  employees: loadEmployees,
  settings: loadSettings,
};

function navigate(hash) {
  const page = hash.replace('#', '') || 'dashboard';
  document.querySelectorAll('.nav-link').forEach(a => {
    a.classList.toggle('active', a.getAttribute('href') === '#' + page);
  });
  const loader = routes[page] || loadDashboard;
  document.getElementById('page-content').innerHTML = '<div class="text-center text-gray-400 mt-20">Loading…</div>';
  loader().catch(err => {
    document.getElementById('page-content').innerHTML =
      `<div class="card text-red-600">Error loading page: ${err.message}</div>`;
  });
}

window.addEventListener('hashchange', () => navigate(location.hash));
window.addEventListener('DOMContentLoaded', () => {
  navigate(location.hash || '#dashboard');
  startLiveCounter();
});

// ── Live counter (SSE) ────────────────────────────────────────────────────────

function startLiveCounter() {
  const el = document.getElementById('live-counter');
  try {
    const es = new EventSource('/api/v1/stats/live');
    es.onmessage = e => { el.textContent = `Requests: ${Number(e.data).toLocaleString()}`; };
    es.onerror = () => { el.textContent = 'Live: disconnected'; };
  } catch (_) {}
}

// ── Dashboard ─────────────────────────────────────────────────────────────────

async function loadDashboard() {
  const [health, topSites, wbSummary, catBreakdown] = await Promise.all([
    api('/health'),
    api('/reports/top-sites?limit=10'),
    api('/reports/work-break-summary'),
    api('/reports/category-breakdown'),
  ]);

  const totalRequests = health.log_count;
  const workReqs = wbSummary.reduce((s, e) => s + e.work_requests, 0);
  const breakReqs = wbSummary.reduce((s, e) => s + e.break_requests, 0);
  const workPct = totalRequests ? Math.round(workReqs / totalRequests * 100) : 0;

  document.getElementById('page-content').innerHTML = `
    <div class="mb-5">
      <h1 class="text-2xl font-bold text-gray-900">Dashboard</h1>
      <p class="text-sm text-gray-500">Overview of employee web traffic</p>
    </div>

    <!-- KPI cards -->
    <div class="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
      <div class="stat-card">
        <div class="text-xs font-semibold text-gray-500 uppercase tracking-wide">Total Requests</div>
        <div class="text-3xl font-bold text-gray-900 mt-1">${totalRequests.toLocaleString()}</div>
      </div>
      <div class="stat-card">
        <div class="text-xs font-semibold text-gray-500 uppercase tracking-wide">DB Size</div>
        <div class="text-3xl font-bold text-gray-900 mt-1">${health.db_size_mb} MB</div>
      </div>
      <div class="stat-card">
        <div class="text-xs font-semibold text-gray-500 uppercase tracking-wide">Work-time %</div>
        <div class="text-3xl font-bold text-green-600 mt-1">${workPct}%</div>
      </div>
      <div class="stat-card">
        <div class="text-xs font-semibold text-gray-500 uppercase tracking-wide">Break Requests</div>
        <div class="text-3xl font-bold text-yellow-600 mt-1">${breakReqs.toLocaleString()}</div>
      </div>
    </div>

    <!-- Charts row -->
    <div class="grid grid-cols-1 md:grid-cols-3 gap-5 mb-6">
      <div class="card md:col-span-2">
        <div class="font-semibold text-gray-700 mb-3">Top 10 Sites</div>
        <canvas id="topSitesChart" height="220"></canvas>
      </div>
      <div class="card">
        <div class="font-semibold text-gray-700 mb-3">Time Classification</div>
        <canvas id="wbPieChart"></canvas>
        <div class="mt-3 text-sm text-gray-600 space-y-1">
          <div><span class="inline-block w-3 h-3 rounded-full bg-green-500 mr-1"></span>Work: ${workReqs.toLocaleString()}</div>
          <div><span class="inline-block w-3 h-3 rounded-full bg-yellow-400 mr-1"></span>Break: ${breakReqs.toLocaleString()}</div>
          <div><span class="inline-block w-3 h-3 rounded-full bg-gray-300 mr-1"></span>Outside: ${(totalRequests - workReqs - breakReqs).toLocaleString()}</div>
        </div>
      </div>
    </div>

    <!-- Category breakdown -->
    <div class="card">
      <div class="font-semibold text-gray-700 mb-3">Category Breakdown</div>
      <canvas id="catChart" height="90"></canvas>
    </div>
  `;

  // Top Sites chart
  new Chart(document.getElementById('topSitesChart'), {
    type: 'bar',
    data: {
      labels: topSites.map(s => s.domain),
      datasets: [{
        label: 'Requests',
        data: topSites.map(s => s.request_count),
        backgroundColor: topSites.map(s => s.category_color || '#6b7280'),
        borderRadius: 4,
      }]
    },
    options: {
      indexAxis: 'y',
      plugins: { legend: { display: false } },
      scales: { x: { grid: { display: false } }, y: { grid: { display: false } } },
      maintainAspectRatio: false,
    }
  });

  // Work/break pie
  const outside = totalRequests - workReqs - breakReqs;
  new Chart(document.getElementById('wbPieChart'), {
    type: 'doughnut',
    data: {
      labels: ['Work', 'Break', 'Outside'],
      datasets: [{ data: [workReqs, breakReqs, outside], backgroundColor: ['#22c55e', '#facc15', '#d1d5db'] }]
    },
    options: { plugins: { legend: { display: false } } }
  });

  // Category bar
  new Chart(document.getElementById('catChart'), {
    type: 'bar',
    data: {
      labels: catBreakdown.map(c => c.category_name),
      datasets: [{
        label: 'Requests',
        data: catBreakdown.map(c => c.count),
        backgroundColor: catBreakdown.map(c => c.category_color),
        borderRadius: 4,
      }]
    },
    options: {
      plugins: { legend: { display: false } },
      scales: { x: { grid: { display: false } }, y: { grid: { display: false } } },
      maintainAspectRatio: false,
    }
  });
}

// ── Timeline ──────────────────────────────────────────────────────────────────

async function loadTimeline() {
  const employees = await api('/employees');
  document.getElementById('page-content').innerHTML = `
    <div class="mb-5 flex items-center justify-between">
      <div>
        <h1 class="text-2xl font-bold text-gray-900">Timeline</h1>
        <p class="text-sm text-gray-500">Requests per employee over time</p>
      </div>
      <div class="flex gap-2 items-center">
        <select id="tl-employee" class="form-select">
          <option value="">All employees</option>
          ${employees.map(e => `<option value="${e.id}">${e.username}</option>`).join('')}
        </select>
        <select id="tl-bucket" class="form-select">
          <option value="hour">By hour</option>
          <option value="day">By day</option>
        </select>
        <button class="btn btn-primary" onclick="refreshTimeline()">Refresh</button>
      </div>
    </div>
    <div class="card">
      <canvas id="timelineChart" height="320"></canvas>
    </div>
  `;
  await refreshTimeline();
}

let _tlChart = null;
async function refreshTimeline() {
  const emp = document.getElementById('tl-employee')?.value || '';
  const bucket = document.getElementById('tl-bucket')?.value || 'hour';
  const params = new URLSearchParams({ bucket });
  if (emp) params.set('employee_id', emp);

  const data = await api('/reports/timeline?' + params);

  // Aggregate by bucket_start + employee
  const empMap = {};
  const buckets = [...new Set(data.map(d => d.bucket_start))].sort();

  data.forEach(d => {
    const k = d.employee_name || `IP unknown`;
    if (!empMap[k]) empMap[k] = {};
    empMap[k][d.bucket_start] = (empMap[k][d.bucket_start] || 0) + d.count;
  });

  const colors = ['#3b82f6','#ef4444','#10b981','#f59e0b','#8b5cf6','#f97316','#14b8a6','#a855f7'];
  const datasets = Object.entries(empMap).map(([name, vals], i) => ({
    label: name,
    data: buckets.map(b => vals[b] || 0),
    borderColor: colors[i % colors.length],
    backgroundColor: colors[i % colors.length] + '33',
    tension: 0.3,
    fill: true,
  }));

  const ctx = document.getElementById('timelineChart');
  if (_tlChart) _tlChart.destroy();
  _tlChart = new Chart(ctx, {
    type: 'line',
    data: { labels: buckets.map(b => b.replace('T', ' ').slice(0, 16)), datasets },
    options: {
      scales: {
        x: { grid: { display: false } },
        y: { beginAtZero: true, grid: { color: '#f3f4f6' } }
      },
      plugins: { legend: { position: 'bottom' } },
      maintainAspectRatio: false,
    }
  });
}

// ── Traffic Log ───────────────────────────────────────────────────────────────

let _logPage = 1;
let _logFilters = {};

async function loadLog() {
  const employees = await api('/employees');
  _logPage = 1;
  document.getElementById('page-content').innerHTML = `
    <div class="mb-5">
      <h1 class="text-2xl font-bold text-gray-900">Traffic Log</h1>
    </div>
    <!-- Filters -->
    <div class="card mb-4 flex flex-wrap gap-3 items-end">
      <div>
        <label class="text-xs font-medium text-gray-500 block mb-1">Employee</label>
        <select id="log-emp" class="form-select">
          <option value="">All</option>
          ${employees.map(e => `<option value="${e.id}">${e.username}</option>`).join('')}
        </select>
      </div>
      <div>
        <label class="text-xs font-medium text-gray-500 block mb-1">Classification</label>
        <select id="log-cls" class="form-select">
          <option value="">All</option>
          <option value="work">Work</option>
          <option value="break">Break</option>
          <option value="outside">Outside</option>
        </select>
      </div>
      <div>
        <label class="text-xs font-medium text-gray-500 block mb-1">Domain</label>
        <input id="log-domain" class="form-input" placeholder="e.g. youtube.com" />
      </div>
      <button class="btn btn-primary" onclick="applyLogFilters()">Filter</button>
      <button class="btn btn-secondary" onclick="clearLogFilters()">Clear</button>
    </div>
    <div class="card">
      <div class="overflow-x-auto">
        <table class="data-table" id="log-table">
          <thead>
            <tr>
              <th>Time</th><th>Employee</th><th>Domain</th>
              <th>Protocol</th><th>Category</th><th>Classification</th><th>Status</th>
            </tr>
          </thead>
          <tbody id="log-body"><tr><td colspan="7" class="text-center text-gray-400 py-8">Loading…</td></tr></tbody>
        </table>
      </div>
      <div class="mt-4 flex justify-between items-center">
        <span id="log-info" class="text-sm text-gray-500"></span>
        <div class="pagination flex gap-1" id="log-pagination"></div>
      </div>
    </div>
  `;
  await fetchLogPage();
}

async function fetchLogPage() {
  const params = new URLSearchParams({ page: _logPage, limit: 50 });
  if (_logFilters.employee_id) params.set('employee_id', _logFilters.employee_id);
  if (_logFilters.classification) params.set('classification', _logFilters.classification);
  if (_logFilters.domain) params.set('domain', _logFilters.domain);

  const data = await api('/traffic?' + params);
  const tbody = document.getElementById('log-body');
  if (!data.items.length) {
    tbody.innerHTML = '<tr><td colspan="7" class="text-center text-gray-400 py-8">No records found</td></tr>';
  } else {
    tbody.innerHTML = data.items.map(r => `
      <tr>
        <td class="whitespace-nowrap text-xs text-gray-500">${r.timestamp.replace('T', ' ').slice(0, 19)}</td>
        <td>${r.employee ? r.employee.username : `<span class="text-gray-400 text-xs">${r.src_ip}</span>`}</td>
        <td class="font-medium">${r.domain}</td>
        <td class="text-xs uppercase text-gray-500">${r.protocol}</td>
        <td>${r.category ? `<span class="color-dot" style="background:${r.category.color}"></span>${r.category.name}` : '<span class="text-gray-400 text-xs">—</span>'}</td>
        <td><span class="badge badge-${r.time_classification}">${r.time_classification}</span></td>
        <td class="text-xs">${r.status_code || '—'}</td>
      </tr>
    `).join('');
  }
  document.getElementById('log-info').textContent = `${data.total.toLocaleString()} total records`;

  // Pagination
  const pages = data.pages;
  const pg = document.getElementById('log-pagination');
  pg.innerHTML = `
    <button ${_logPage <= 1 ? 'disabled' : ''} onclick="_logPage--;fetchLogPage()">‹ Prev</button>
    <button class="active">${_logPage} / ${pages}</button>
    <button ${_logPage >= pages ? 'disabled' : ''} onclick="_logPage++;fetchLogPage()">Next ›</button>
  `;
}

function applyLogFilters() {
  _logFilters.employee_id = document.getElementById('log-emp').value;
  _logFilters.classification = document.getElementById('log-cls').value;
  _logFilters.domain = document.getElementById('log-domain').value;
  _logPage = 1;
  fetchLogPage();
}

function clearLogFilters() {
  _logFilters = {};
  _logPage = 1;
  document.getElementById('log-emp').value = '';
  document.getElementById('log-cls').value = '';
  document.getElementById('log-domain').value = '';
  fetchLogPage();
}

// ── Reports ───────────────────────────────────────────────────────────────────

async function loadReports() {
  const employees = await api('/employees');
  document.getElementById('page-content').innerHTML = `
    <div class="mb-5 flex items-center justify-between">
      <h1 class="text-2xl font-bold text-gray-900">Reports</h1>
      <div class="flex gap-2">
        <a href="/api/v1/export/csv" class="btn btn-secondary" download>⬇ CSV</a>
        <a href="/api/v1/export/pdf" class="btn btn-secondary" download>⬇ PDF</a>
      </div>
    </div>

    <!-- Filter bar -->
    <div class="card mb-5 flex flex-wrap gap-3 items-end">
      <div>
        <label class="text-xs font-medium text-gray-500 block mb-1">Employee</label>
        <select id="rpt-emp" class="form-select">
          <option value="">All</option>
          ${employees.map(e => `<option value="${e.id}">${e.username}</option>`).join('')}
        </select>
      </div>
      <div>
        <label class="text-xs font-medium text-gray-500 block mb-1">Classification</label>
        <select id="rpt-cls" class="form-select">
          <option value="">All</option>
          <option value="work">Work</option>
          <option value="break">Break</option>
          <option value="outside">Outside</option>
        </select>
      </div>
      <button class="btn btn-primary" onclick="loadReportData()">Apply</button>
    </div>

    <!-- Work/break per employee -->
    <div class="card mb-5">
      <div class="font-semibold text-gray-700 mb-3">Work vs Break per Employee</div>
      <canvas id="wbBarChart" height="120"></canvas>
    </div>

    <!-- Top sites per employee table -->
    <div class="card">
      <div class="font-semibold text-gray-700 mb-3">Top Sites per Employee</div>
      <div id="top-sites-by-emp">Loading…</div>
    </div>
  `;
  await loadReportData();
}

let _wbChart = null;
async function loadReportData() {
  const emp = document.getElementById('rpt-emp')?.value || '';
  const cls = document.getElementById('rpt-cls')?.value || '';
  const params = new URLSearchParams();
  if (emp) params.set('employee_id', emp);
  if (cls) params.set('classification', cls);

  const [wbData, topByEmp] = await Promise.all([
    api('/reports/work-break-summary?' + params),
    api('/reports/top-sites-by-employee?' + params + '&limit=5'),
  ]);

  // Stacked bar
  const ctx = document.getElementById('wbBarChart');
  if (_wbChart) _wbChart.destroy();
  _wbChart = new Chart(ctx, {
    type: 'bar',
    data: {
      labels: wbData.map(e => e.employee_name || 'Unknown'),
      datasets: [
        { label: 'Work', data: wbData.map(e => e.work_requests), backgroundColor: '#22c55e' },
        { label: 'Break', data: wbData.map(e => e.break_requests), backgroundColor: '#facc15' },
        { label: 'Outside', data: wbData.map(e => e.outside_requests), backgroundColor: '#d1d5db' },
      ]
    },
    options: {
      scales: { x: { stacked: true }, y: { stacked: true, grid: { color: '#f3f4f6' } } },
      plugins: { legend: { position: 'bottom' } },
      maintainAspectRatio: false,
    }
  });

  // Top sites table
  const container = document.getElementById('top-sites-by-emp');
  if (!topByEmp.length) {
    container.innerHTML = '<p class="text-gray-400">No data</p>';
    return;
  }
  container.innerHTML = topByEmp.map(row => `
    <div class="mb-4">
      <div class="font-medium text-gray-800 mb-1">${row.employee.username}</div>
      <table class="data-table">
        <thead><tr><th>#</th><th>Domain</th><th>Requests</th></tr></thead>
        <tbody>
          ${row.sites.slice(0, 5).map((s, i) => `
            <tr><td class="text-gray-400">${i+1}</td><td>${s.domain}</td><td>${s.count.toLocaleString()}</td></tr>
          `).join('')}
        </tbody>
      </table>
    </div>
  `).join('');
}

// ── Employees ─────────────────────────────────────────────────────────────────

async function loadEmployees() {
  const employees = await api('/employees');
  document.getElementById('page-content').innerHTML = `
    <div class="mb-5 flex items-center justify-between">
      <h1 class="text-2xl font-bold text-gray-900">Employees</h1>
      <button class="btn btn-primary" onclick="showAddEmployee()">+ Add Employee</button>
    </div>
    <div id="emp-add-form" class="card mb-4 hidden">
      <div class="font-semibold mb-3">Add Employee</div>
      <div class="flex gap-3 items-end flex-wrap">
        <div>
          <label class="text-xs font-medium text-gray-500 block mb-1">Username</label>
          <input id="new-emp-name" class="form-input" placeholder="john.doe" />
        </div>
        <div>
          <label class="text-xs font-medium text-gray-500 block mb-1">Email (optional)</label>
          <input id="new-emp-email" class="form-input" placeholder="john@company.com" />
        </div>
        <button class="btn btn-primary" onclick="saveEmployee()">Save</button>
        <button class="btn btn-secondary" onclick="document.getElementById('emp-add-form').classList.add('hidden')">Cancel</button>
      </div>
    </div>
    <div class="space-y-4" id="emp-list">
      ${employees.length === 0 ? '<div class="card text-gray-400 text-center py-8">No employees added yet. Click "Add Employee" to get started.</div>' :
        employees.map(e => renderEmployeeCard(e)).join('')}
    </div>
  `;
}

function renderEmployeeCard(e) {
  const ips = e.ips || [];
  return `
    <div class="card" id="emp-card-${e.id}">
      <div class="flex items-center justify-between mb-3">
        <div>
          <div class="font-semibold text-gray-800">${e.username}</div>
          <div class="text-sm text-gray-400">${e.email || '—'}</div>
        </div>
        <button class="btn btn-danger text-xs" onclick="deleteEmployee(${e.id})">Remove</button>
      </div>
      <div class="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">IP Addresses</div>
      <div class="space-y-1 mb-3" id="ip-list-${e.id}">
        ${ips.map(ip => `
          <div class="flex items-center gap-2">
            <span class="font-mono text-sm bg-gray-100 rounded px-2 py-0.5">${ip.ip_address}</span>
            <span class="text-xs text-gray-400">${ip.label || ''}</span>
            <button class="text-red-400 text-xs hover:text-red-600" onclick="deleteIP(${e.id}, ${ip.id})">✕</button>
          </div>
        `).join('') || '<div class="text-gray-400 text-xs">No IPs mapped</div>'}
      </div>
      <div class="flex gap-2">
        <input id="ip-input-${e.id}" class="form-input text-sm" placeholder="192.168.1.10" style="width:160px" />
        <input id="ip-label-${e.id}" class="form-input text-sm" placeholder="Label (e.g. Laptop)" style="width:160px" />
        <button class="btn btn-secondary text-xs" onclick="addIP(${e.id})">+ Add IP</button>
      </div>
    </div>
  `;
}

function showAddEmployee() {
  document.getElementById('emp-add-form').classList.remove('hidden');
}

async function saveEmployee() {
  const name = document.getElementById('new-emp-name').value.trim();
  if (!name) return alert('Username is required');
  const email = document.getElementById('new-emp-email').value.trim();
  await fetch('/api/v1/employees', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username: name, email: email || null }),
  });
  loadEmployees();
}

async function deleteEmployee(id) {
  if (!confirm('Remove this employee? Their traffic history will be kept but unlinked.')) return;
  await fetch(`/api/v1/employees/${id}`, { method: 'DELETE' });
  loadEmployees();
}

async function addIP(empId) {
  const ip = document.getElementById(`ip-input-${empId}`).value.trim();
  const label = document.getElementById(`ip-label-${empId}`).value.trim();
  if (!ip) return alert('IP address is required');
  await fetch(`/api/v1/employees/${empId}/ips`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ip_address: ip, label: label || null }),
  });
  loadEmployees();
}

async function deleteIP(empId, ipId) {
  await fetch(`/api/v1/employees/${empId}/ips/${ipId}`, { method: 'DELETE' });
  loadEmployees();
}

// ── Settings ──────────────────────────────────────────────────────────────────

async function loadSettings() {
  const [schedule, categories] = await Promise.all([
    api('/schedule'),
    api('/categories'),
  ]);

  const breaks = schedule.breaks || [];
  document.getElementById('page-content').innerHTML = `
    <h1 class="text-2xl font-bold text-gray-900 mb-6">Settings</h1>

    <!-- CA Cert -->
    <div class="card mb-5">
      <div class="font-semibold text-gray-700 mb-2">CA Certificate</div>
      <p class="text-sm text-gray-500 mb-3">Employees must install this certificate to enable HTTPS monitoring.</p>
      <a href="/ca-cert.pem" class="btn btn-secondary" download>⬇ Download CA Certificate</a>
      <div class="mt-3 text-sm text-gray-600 space-y-1">
        <div><b>Windows:</b> Double-click .crt → Import to "Trusted Root Certification Authorities"</div>
        <div><b>macOS:</b> Double-click → Keychain Access → Set to "Always Trust"</div>
        <div><b>Firefox:</b> about:preferences#privacy → View Certificates → Import</div>
      </div>
      <div class="mt-3 p-3 bg-gray-50 rounded-lg text-sm font-mono text-gray-600">
        Proxy address: <b>${location.hostname}:8080</b>
      </div>
    </div>

    <!-- Work Schedule -->
    <div class="card mb-5">
      <div class="font-semibold text-gray-700 mb-3">Work Schedule</div>
      <div class="grid grid-cols-2 gap-4 mb-4">
        <div>
          <label class="text-xs font-medium text-gray-500 block mb-1">Timezone</label>
          <input id="sch-tz" class="form-input w-full" value="${schedule.timezone}" />
        </div>
        <div>
          <label class="text-xs font-medium text-gray-500 block mb-1">Work Days (JSON array, 1=Mon)</label>
          <input id="sch-days" class="form-input w-full" value="${schedule.work_days}" />
        </div>
        <div>
          <label class="text-xs font-medium text-gray-500 block mb-1">Work Start</label>
          <input id="sch-start" type="time" class="form-input w-full" value="${schedule.work_start}" />
        </div>
        <div>
          <label class="text-xs font-medium text-gray-500 block mb-1">Work End</label>
          <input id="sch-end" type="time" class="form-input w-full" value="${schedule.work_end}" />
        </div>
      </div>
      <div class="font-medium text-gray-600 text-sm mb-2">Break Windows</div>
      <div id="breaks-list" class="space-y-2 mb-3">
        ${breaks.map((b, i) => `
          <div class="flex gap-2 items-center" id="break-row-${i}">
            <input class="form-input" placeholder="Label" value="${b.label}" id="brk-label-${i}" style="width:120px" />
            <input type="time" class="form-input" value="${b.break_start}" id="brk-start-${i}" />
            <span class="text-gray-400">to</span>
            <input type="time" class="form-input" value="${b.break_end}" id="brk-end-${i}" />
            <button class="text-red-400 hover:text-red-600 text-sm" onclick="document.getElementById('break-row-${i}').remove()">✕</button>
          </div>
        `).join('')}
      </div>
      <div class="flex gap-2">
        <button class="btn btn-secondary text-sm" onclick="addBreakRow()">+ Add Break</button>
        <button class="btn btn-primary" onclick="saveSchedule()">Save Schedule</button>
      </div>
    </div>

    <!-- Categories -->
    <div class="card">
      <div class="font-semibold text-gray-700 mb-3">Categories</div>
      <div class="mb-3">
        <label class="text-xs font-medium text-gray-500 block mb-1">Test a domain</label>
        <div class="flex gap-2">
          <input id="test-domain" class="form-input" placeholder="youtube.com" />
          <button class="btn btn-secondary" onclick="testDomain()">Test</button>
        </div>
        <div id="test-result" class="mt-1 text-sm text-gray-600"></div>
      </div>
      <table class="data-table">
        <thead><tr><th>Category</th><th>Color</th><th>Rules</th></tr></thead>
        <tbody>
          ${categories.map(c => `
            <tr>
              <td><span class="color-dot" style="background:${c.color}"></span>${c.name}</td>
              <td>${c.color}</td>
              <td class="text-xs text-gray-400">${c.rules.length} rule(s)</td>
            </tr>
          `).join('')}
        </tbody>
      </table>
    </div>
  `;
}

let _breakCount = 0;
function addBreakRow() {
  _breakCount++;
  const i = 'new-' + _breakCount;
  const div = document.createElement('div');
  div.className = 'flex gap-2 items-center';
  div.id = `break-row-${i}`;
  div.innerHTML = `
    <input class="form-input" placeholder="Label" id="brk-label-${i}" style="width:120px" />
    <input type="time" class="form-input" id="brk-start-${i}" value="10:00" />
    <span class="text-gray-400">to</span>
    <input type="time" class="form-input" id="brk-end-${i}" value="10:15" />
    <button class="text-red-400 hover:text-red-600 text-sm" onclick="document.getElementById('break-row-${i}').remove()">✕</button>
  `;
  document.getElementById('breaks-list').appendChild(div);
}

async function saveSchedule() {
  const breaks = [];
  document.querySelectorAll('[id^="break-row-"]').forEach(row => {
    const i = row.id.replace('break-row-', '');
    const label = document.getElementById(`brk-label-${i}`)?.value || 'Break';
    const start = document.getElementById(`brk-start-${i}`)?.value;
    const end = document.getElementById(`brk-end-${i}`)?.value;
    if (start && end) breaks.push({ label, break_start: start, break_end: end });
  });

  const payload = {
    timezone: document.getElementById('sch-tz').value,
    work_days: document.getElementById('sch-days').value,
    work_start: document.getElementById('sch-start').value,
    work_end: document.getElementById('sch-end').value,
    breaks,
  };

  const res = await fetch('/api/v1/schedule', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (res.ok) alert('Schedule saved!');
  else alert('Failed to save schedule: ' + res.status);
}

async function testDomain() {
  const domain = document.getElementById('test-domain').value.trim();
  if (!domain) return;
  const data = await api(`/categories/test-domain?domain=${encodeURIComponent(domain)}`);
  document.getElementById('test-result').textContent =
    data.matched_category ? `Matched: ${data.matched_category}` : 'No match — will be "uncategorized"';
}
