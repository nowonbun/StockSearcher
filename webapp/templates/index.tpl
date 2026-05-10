<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Stock AI Portal</title>

  <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/materialize/1.0.0/css/materialize.min.css">
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/ag-grid-community@31.3.2/styles/ag-grid.css">
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/ag-grid-community@31.3.2/styles/ag-theme-balham.css">

  {literal}
  <style>
    /* ── 색상 변수 ── */
    :root {
      --bg:    #060e20;
      --panel: #0b1a36;
      --line:  #1d345f;
      --txt:   #d7e4ff;
      --acc:   #1c7dff;
    }

    /* ── 기본 ── */
    body {
      margin: 0;
      background: radial-gradient(circle at 20% 0%, #0d2247, #060e20 52%);
      color: var(--txt);
      font-family: Inter, Roboto, sans-serif;
    }

    .layout {
      display: grid;
      grid-template-columns: 220px 1fr;
      min-height: 100vh;
    }

    /* ── 사이드바 ── */
    .side {
      border-right: 1px solid #15305d;
      padding: 18px 14px;
      background: linear-gradient(180deg, #081733, #050d1f);
    }

    .brand {
      font-size: 24px;
      font-weight: 700;
    }

    .brand-sub {
      color: #85a3d4;
      font-size: 12px;
      margin-top: 4px;
    }

    .side-menu {
      margin-top: 28px;
    }

    .side-menu ul {
      padding: 0;
      margin: 0;
      list-style: none;
    }

    .side-menu li {
      display: flex;
      align-items: center;
      padding: 11px 14px;
      border-radius: 10px;
      color: #7a9cc8;
      cursor: pointer;
      font-size: 14px;
      font-weight: 500;
      transition: background .15s, color .15s;
    }

    .side-menu li:hover {
      background: #0d2048;
      color: #b8d0f4;
    }

    .side-menu li.active {
      background: #12366f;
      color: #dce8ff;
    }

    .sidebar-heading {
      padding: 16px 14px 4px;
      font-size: 11px;
      font-weight: 700;
      letter-spacing: 0.08em;
      text-transform: uppercase;
      color: #4a6899;
      cursor: default;
    }

    .sidebar-heading:hover {
      background: transparent !important;
      color: #4a6899 !important;
    }

    /* ── 메인 콘텐츠 ── */
    .content {
      padding: 24px;
    }

    /* ── 패널 전환 (사이드바) ── */
    .panel {
      display: none;
    }

    /* ── 로딩 스피너 ── */
    .loading-spinner {
      width: 40px;
      height: 40px;
      border: 3px solid rgba(138,170,212,0.2);
      border-top-color: #4a9adc;
      border-radius: 50%;
      animation: spin 0.7s linear infinite;
    }
    @keyframes spin {
      to { transform: rotate(360deg); }
    }

    .panel.active {
      display: block;
    }

    /* ── 공통 버튼 ── */
    .btnx {
      background: #176af2;
      color: #fff;
      border: none;
      border-radius: 10px;
      padding: 10px 18px;
      cursor: pointer;
      font-size: 13px;
      white-space: nowrap;
    }

    .btnx-outline {
      background: transparent;
      color: #7a9cc8;
      border: 1px solid #2a4270;
      border-radius: 10px;
      padding: 9px 14px;
      cursor: pointer;
      font-size: 13px;
      white-space: nowrap;
    }

    .btnx-outline:hover {
      background: #0d2048;
      color: #b8d0f4;
    }

    .panel-title {
      font-size: 18px;
      font-weight: 700;
      margin: 0 0 16px;
      color: #c4d8ff;
    }

    /* ── Materialize 폼 다크 오버라이드 ── */
    .row .input-field input,
    .row .input-field .select-wrapper input.select-dropdown {
      color: #dbe7ff !important;
      border-bottom: 1px solid #2a4270 !important;
    }

    .row .input-field label {
      color: #8da8d1 !important;
    }

    /* ── Predict 탭 (JP / KR) ── */
    .predict-tabs {
      display: flex;
      gap: 4px;
      border-bottom: 1px solid var(--line);
      margin-bottom: 0;
    }

    .ptab-btn,
    .stab-btn,
    .ptab-w-btn,
    .stab-w-btn {
      background: transparent;
      border: none;
      border-bottom: 3px solid transparent;
      padding: 8px 24px;
      margin-bottom: -1px;
      color: #6a8cc5;
      font-size: 14px;
      font-weight: 600;
      cursor: pointer;
      transition: color .15s;
    }

    .ptab-btn:hover,
    .stab-btn:hover,
    .ptab-w-btn:hover,
    .stab-w-btn:hover {
      color: var(--txt);
    }

    .ptab-btn.active,
    .stab-btn.active,
    .ptab-w-btn.active,
    .stab-w-btn.active {
      color: var(--txt);
      border-bottom-color: var(--acc);
    }

    .ptab-panel,
    .stab-panel,
    .ptab-w-panel,
    .stab-w-panel {
      display: none;
    }

    .ptab-panel.active,
    .stab-panel.active,
    .ptab-w-panel.active,
    .stab-w-panel.active {
      display: block;
    }

    /* ── 검색 폼 박스 ── */
    .search-form {
      background: linear-gradient(180deg, #0b1a36, #09152f);
      border: 1px solid #1d345f;
      border-top: none;
      border-radius: 0 0 12px 12px;
      padding: 12px 16px 2px;
      margin-bottom: 14px;
    }

    .filter-actions {
      display: flex;
      gap: 8px;
      align-items: flex-end;
      padding-bottom: 16px;
    }

    /* ── Scanner 검색 폼 ── */
    .scanner-form {
      background: linear-gradient(180deg, #0b1a36, #09152f);
      border: 1px solid #1d345f;
      border-radius: 14px;
      padding: 12px 16px 0;
      margin-bottom: 16px;
    }

    /* ── Batch 패널 ── */
    .batch-group {
      margin: 20px 0;
    }

    .batch-group-label {
      font-size: 11px;
      font-weight: 700;
      letter-spacing: 0.08em;
      text-transform: uppercase;
      color: #85a3d4;
      margin-bottom: 10px;
      display: flex;
      align-items: center;
      gap: 10px;
    }

    .batch-btn-row {
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
    }

    .batch-task-item {
      display: flex;
      align-items: center;
      gap: 12px;
      padding: 8px 14px;
      background: #0b1a36;
      border: 1px solid #1d345f;
      border-radius: 8px;
      margin-bottom: 6px;
      font-size: 13px;
    }

    .batch-task-name { font-weight: 600; color: #c4d8ff; min-width: 100px; }
    .status-running  { color: #4caf50; }
    .status-success  { color: #85a3d4; }
    .status-failed   { color: #ef5350; }

    .batch-log-item {
      padding: 6px 12px;
      background: #0b1a36;
      border: 1px solid #1d345f;
      border-radius: 6px;
      margin-bottom: 4px;
      font-size: 12px;
      cursor: pointer;
      color: #85a3d4;
      transition: background .15s;
    }

    .batch-log-item:hover, .batch-log-item.active {
      background: #12306a;
      color: #c4d8ff;
    }

    #batch-log-content {
      background: #020a1a;
      border: 1px solid #1d345f;
      border-radius: 8px;
      padding: 12px 16px;
      font-size: 12px;
      color: #a0c0e8;
      white-space: pre-wrap;
      word-break: break-all;
      max-height: 420px;
      overflow-y: auto;
      margin-top: 10px;
      display: none;
      font-family: monospace;
    }

    /* ── AG-Grid 다크 색상 오버라이드 (balham 라이트 테마 위에 적용) ── */
    .ag-theme-balham {
      --ag-background-color:         #07102a;
      --ag-odd-row-background-color: #091432;
      --ag-header-background-color:  #0b1a40;
      --ag-header-foreground-color:  #c4d8ff;
      --ag-foreground-color:         #d7e4ff;
      --ag-border-color:             #1d345f;
      --ag-row-hover-color:          #12306a;
      --ag-selected-row-background-color: #12366f;
      --ag-input-border-color:       #2a4270;
    }
  </style>
  {/literal}
</head>
<body>

<div class="layout">

  <!-- ══ 사이드바 ══ -->
  <aside class="side">
    <div class="brand">Stock AI Portal</div>
    <div class="brand-sub">AI-Powered Stock Analysis</div>

    <div class="side-menu">
      <ul>
        <li class="sidebar-heading">관리</li>
        <li data-panel="panel-batch">Batch Control</li>
        <li class="sidebar-heading">일봉</li>
        <li class="active" data-panel="panel-predict">Predict Search</li>
        <li data-panel="panel-scanner">UpperBand Scanner</li>
        <li class="sidebar-heading">주봉</li>
        <li data-panel="panel-predict-weekly">Predict Search</li>
        <li data-panel="panel-scanner-weekly">UpperBand Scanner</li>
      </ul>
    </div>
  </aside>

  <!-- ══ 메인 콘텐츠 ══ -->
  <main class="content">

    {if $message}
      <p style="color:#ff7a9d; margin: 0 0 12px">{$message|escape}</p>
    {/if}

    <!-- ── Predict Search 패널 ── -->
    <div id="panel-predict" class="panel active">
      <div class="panel-title">Predict Search</div>

      <!-- JP / KR 탭 버튼 -->
      <div class="predict-tabs">
        <button class="ptab-btn active" data-ptab="ptab-jp">JP</button>
        <button class="ptab-btn"        data-ptab="ptab-kr">KR</button>
      </div>

      <!-- JP 탭 -->
      <div id="ptab-jp" class="ptab-panel active">
        <div class="search-form">
          <!-- 1행: Date Cutoff + Search + 버튼 -->
          <div class="row" style="margin-bottom: 0">
            <div class="input-field col s12 m4">
              <select id="as-of-jp"></select>
              <label>Date Cutoff</label>
            </div>
            <div class="input-field col s12 m4">
              <input id="jp-search" type="text">
              <label for="jp-search">Search</label>
            </div>
            <div class="col s12 m4">
              <div class="filter-actions">
                <button id="predict-jp-btn" class="btnx">검색</button>
                <button id="jp-clear-btn"   class="btnx-outline">초기화</button>
              </div>
            </div>
          </div>
          <!-- 2행: Open/Close 범위 필터 -->
          <div class="row" style="margin-bottom: 0">
            <div class="input-field col s6 m3">
              <input id="jp-open-min" type="number" step="any">
              <label for="jp-open-min">Open min</label>
            </div>
            <div class="input-field col s6 m3">
              <input id="jp-open-max" type="number" step="any">
              <label for="jp-open-max">Open max</label>
            </div>
            <div class="input-field col s6 m3">
              <input id="jp-close-min" type="number" step="any">
              <label for="jp-close-min">Close min</label>
            </div>
            <div class="input-field col s6 m3">
              <input id="jp-close-max" type="number" step="any">
              <label for="jp-close-max">Close max</label>
            </div>
          </div>
        </div>
        <div id="predict-grid-jp" class="ag-theme-balham" style="height: 520px; width: 100%"></div>
      </div>

      <!-- KR 탭 -->
      <div id="ptab-kr" class="ptab-panel">
        <div class="search-form">
          <!-- 1행: Date Cutoff + Search + 버튼 -->
          <div class="row" style="margin-bottom: 0">
            <div class="input-field col s12 m4">
              <select id="as-of-kr"></select>
              <label>Date Cutoff</label>
            </div>
            <div class="input-field col s12 m4">
              <input id="kr-search" type="text">
              <label for="kr-search">Search</label>
            </div>
            <div class="col s12 m4">
              <div class="filter-actions">
                <button id="predict-kr-btn" class="btnx">검색</button>
                <button id="kr-clear-btn"   class="btnx-outline">초기화</button>
              </div>
            </div>
          </div>
          <!-- 2행: Open/Close 범위 필터 -->
          <div class="row" style="margin-bottom: 0">
            <div class="input-field col s6 m3">
              <input id="kr-open-min" type="number" step="any">
              <label for="kr-open-min">Open min</label>
            </div>
            <div class="input-field col s6 m3">
              <input id="kr-open-max" type="number" step="any">
              <label for="kr-open-max">Open max</label>
            </div>
            <div class="input-field col s6 m3">
              <input id="kr-close-min" type="number" step="any">
              <label for="kr-close-min">Close min</label>
            </div>
            <div class="input-field col s6 m3">
              <input id="kr-close-max" type="number" step="any">
              <label for="kr-close-max">Close max</label>
            </div>
          </div>
        </div>
        <div id="predict-grid-kr" class="ag-theme-balham" style="height: 520px; width: 100%"></div>
      </div>

    </div>

    <!-- ── UpperBand Scanner 패널 ── -->
    <div id="panel-scanner" class="panel">
      <div class="panel-title">UpperBand Scanner</div>

      <!-- JP / KR 탭 버튼 -->
      <div class="predict-tabs">
        <button class="stab-btn active" data-stab="stab-jp">JP</button>
        <button class="stab-btn"        data-stab="stab-kr">KR</button>
      </div>

      <!-- JP 탭 -->
      <div id="stab-jp" class="stab-panel active">
        <div class="search-form">
          <div class="row" style="margin-bottom: 0">
            <div class="input-field col s12 m4">
              <select id="scanner-jp-date"></select>
              <label>Date</label>
            </div>
            <div class="input-field col s12 m3">
              <input id="scanner-jp-trans-amount" type="text">
              <label for="scanner-jp-trans-amount">trans_amnt_min</label>
            </div>
            <div class="input-field col s12 m3">
              <input id="scanner-jp-close-max" type="text">
              <label for="scanner-jp-close-max">close_max</label>
            </div>
            <div class="col s12 m2">
              <div class="filter-actions">
                <button id="scanner-jp-btn" class="btnx">검색</button>
              </div>
            </div>
          </div>
        </div>
        <div id="scanner-grid-jp" class="ag-theme-balham" style="height: 520px; width: 100%"></div>
      </div>

      <!-- KR 탭 -->
      <div id="stab-kr" class="stab-panel">
        <div class="search-form">
          <div class="row" style="margin-bottom: 0">
            <div class="input-field col s12 m4">
              <select id="scanner-kr-date"></select>
              <label>Date</label>
            </div>
            <div class="input-field col s12 m3">
              <input id="scanner-kr-trans-amount" type="text">
              <label for="scanner-kr-trans-amount">trans_amnt_min</label>
            </div>
            <div class="input-field col s12 m3">
              <input id="scanner-kr-close-max" type="text">
              <label for="scanner-kr-close-max">close_max</label>
            </div>
            <div class="col s12 m2">
              <div class="filter-actions">
                <button id="scanner-kr-btn" class="btnx">검색</button>
              </div>
            </div>
          </div>
        </div>
        <div id="scanner-grid-kr" class="ag-theme-balham" style="height: 520px; width: 100%"></div>
      </div>

    </div>

    <!-- ── Predict Search 주봉 패널 ── -->
    <div id="panel-predict-weekly" class="panel">
      <div class="panel-title">Predict Search <span style="font-size:13px;color:#85a3d4">(주봉)</span></div>

      <div class="predict-tabs">
        <button class="ptab-w-btn active" data-ptabw="ptab-w-jp">JP</button>
        <button class="ptab-w-btn"        data-ptabw="ptab-w-kr">KR</button>
      </div>

      <!-- JP 탭 -->
      <div id="ptab-w-jp" class="ptab-w-panel active">
        <div class="search-form">
          <div class="row" style="margin-bottom: 0">
            <div class="input-field col s12 m4">
              <select id="as-of-jp-w"></select>
              <label>Date Cutoff</label>
            </div>
            <div class="input-field col s12 m4">
              <input id="jp-w-search" type="text">
              <label for="jp-w-search">Search</label>
            </div>
            <div class="col s12 m4">
              <div class="filter-actions">
                <button id="predict-jp-w-btn" class="btnx">검색</button>
                <button id="jp-w-clear-btn"   class="btnx-outline">초기화</button>
              </div>
            </div>
          </div>
          <div class="row" style="margin-bottom: 0">
            <div class="input-field col s6 m3">
              <input id="jp-w-open-min" type="number" step="any">
              <label for="jp-w-open-min">Open min</label>
            </div>
            <div class="input-field col s6 m3">
              <input id="jp-w-open-max" type="number" step="any">
              <label for="jp-w-open-max">Open max</label>
            </div>
            <div class="input-field col s6 m3">
              <input id="jp-w-close-min" type="number" step="any">
              <label for="jp-w-close-min">Close min</label>
            </div>
            <div class="input-field col s6 m3">
              <input id="jp-w-close-max" type="number" step="any">
              <label for="jp-w-close-max">Close max</label>
            </div>
          </div>
        </div>
        <div id="predict-grid-jp-w" class="ag-theme-balham" style="height: 520px; width: 100%"></div>
      </div>

      <!-- KR 탭 -->
      <div id="ptab-w-kr" class="ptab-w-panel">
        <div class="search-form">
          <div class="row" style="margin-bottom: 0">
            <div class="input-field col s12 m4">
              <select id="as-of-kr-w"></select>
              <label>Date Cutoff</label>
            </div>
            <div class="input-field col s12 m4">
              <input id="kr-w-search" type="text">
              <label for="kr-w-search">Search</label>
            </div>
            <div class="col s12 m4">
              <div class="filter-actions">
                <button id="predict-kr-w-btn" class="btnx">검색</button>
                <button id="kr-w-clear-btn"   class="btnx-outline">초기화</button>
              </div>
            </div>
          </div>
          <div class="row" style="margin-bottom: 0">
            <div class="input-field col s6 m3">
              <input id="kr-w-open-min" type="number" step="any">
              <label for="kr-w-open-min">Open min</label>
            </div>
            <div class="input-field col s6 m3">
              <input id="kr-w-open-max" type="number" step="any">
              <label for="kr-w-open-max">Open max</label>
            </div>
            <div class="input-field col s6 m3">
              <input id="kr-w-close-min" type="number" step="any">
              <label for="kr-w-close-min">Close min</label>
            </div>
            <div class="input-field col s6 m3">
              <input id="kr-w-close-max" type="number" step="any">
              <label for="kr-w-close-max">Close max</label>
            </div>
          </div>
        </div>
        <div id="predict-grid-kr-w" class="ag-theme-balham" style="height: 520px; width: 100%"></div>
      </div>

    </div>

    <!-- ── UpperBand Scanner 주봉 패널 ── -->
    <div id="panel-scanner-weekly" class="panel">
      <div class="panel-title">UpperBand Scanner <span style="font-size:13px;color:#85a3d4">(주봉)</span></div>

      <div class="predict-tabs">
        <button class="stab-w-btn active" data-stabw="stab-w-jp">JP</button>
        <button class="stab-w-btn"        data-stabw="stab-w-kr">KR</button>
      </div>

      <!-- JP 탭 -->
      <div id="stab-w-jp" class="stab-w-panel active">
        <div class="search-form">
          <div class="row" style="margin-bottom: 0">
            <div class="input-field col s12 m4">
              <select id="scanner-w-jp-date"></select>
              <label>Date</label>
            </div>
            <div class="input-field col s12 m3">
              <input id="scanner-w-jp-trans-amount" type="text">
              <label for="scanner-w-jp-trans-amount">trans_amnt_min</label>
            </div>
            <div class="input-field col s12 m3">
              <input id="scanner-w-jp-close-max" type="text">
              <label for="scanner-w-jp-close-max">close_max</label>
            </div>
            <div class="col s12 m2">
              <div class="filter-actions">
                <button id="scanner-w-jp-btn" class="btnx">검색</button>
              </div>
            </div>
          </div>
        </div>
        <div id="scanner-grid-jp-w" class="ag-theme-balham" style="height: 520px; width: 100%"></div>
      </div>

      <!-- KR 탭 -->
      <div id="stab-w-kr" class="stab-w-panel">
        <div class="search-form">
          <div class="row" style="margin-bottom: 0">
            <div class="input-field col s12 m4">
              <select id="scanner-w-kr-date"></select>
              <label>Date</label>
            </div>
            <div class="input-field col s12 m3">
              <input id="scanner-w-kr-trans-amount" type="text">
              <label for="scanner-w-kr-trans-amount">trans_amnt_min</label>
            </div>
            <div class="input-field col s12 m3">
              <input id="scanner-w-kr-close-max" type="text">
              <label for="scanner-w-kr-close-max">close_max</label>
            </div>
            <div class="col s12 m2">
              <div class="filter-actions">
                <button id="scanner-w-kr-btn" class="btnx">검색</button>
              </div>
            </div>
          </div>
        </div>
        <div id="scanner-grid-kr-w" class="ag-theme-balham" style="height: 520px; width: 100%"></div>
      </div>

    </div>

    <!-- ── Batch Control 패널 ── -->
    <div id="panel-batch" class="panel">
      <div class="panel-title">Batch Control</div>

      <div class="batch-group">
        <div class="batch-group-label">JP</div>
        <div class="batch-btn-row">
          <button class="btnx batch-run-btn" data-task="dataset_jp">dataset_jp</button>
          <button class="btnx batch-run-btn" data-task="predict_jp">predict_jp</button>
          <button class="btnx batch-run-btn" data-task="job_jp">JP 전체</button>
        </div>
      </div>

      <div class="batch-group">
        <div class="batch-group-label">KR</div>
        <div class="batch-btn-row">
          <button class="btnx batch-run-btn" data-task="dataset_kr">dataset_kr</button>
          <button class="btnx batch-run-btn" data-task="predict_kr">predict_kr</button>
          <button class="btnx batch-run-btn" data-task="job_kr">KR 전체</button>
        </div>
      </div>

      <div class="batch-group">
        <div class="batch-group-label">
          Tasks
          <button class="btnx-outline" id="refresh-tasks" style="font-size:11px;padding:4px 10px">새로고침</button>
        </div>
        <div id="batch-task-list"></div>
      </div>

      <div class="batch-group">
        <div class="batch-group-label">Logs</div>
        <div id="batch-log-list"></div>
        <pre id="batch-log-content"></pre>
      </div>
    </div>

  </main>
</div>

<!-- ── 로딩 오버레이 ── -->
<div id="loading-overlay" style="display:none; position:fixed; top:0; left:0; width:100%; height:100%; background:rgba(10,18,28,0.55); z-index:900; align-items:center; justify-content:center; flex-direction:column; gap:14px;">
  <div class="loading-spinner"></div>
  <div style="color:#8baad4; font-size:13px; letter-spacing:0.04em">로딩 중...</div>
</div>

<!-- ── 차트 모달 ── -->
<div id="chart-modal" style="display:none; position:fixed; top:0; left:0; width:100%; height:100%; background:rgba(0,0,0,0.78); z-index:1000; align-items:center; justify-content:center;">
  <div style="background:#1e2a3a; width:93%; max-width:1300px; height:84vh; position:relative; border-radius:8px; padding:14px 16px; display:flex; flex-direction:column; box-shadow:0 8px 32px rgba(0,0,0,0.6);">
    <div style="display:flex; align-items:center; margin-bottom:8px; gap:12px;">
      <span id="chart-title" style="color:#c9d8ef; font-size:13px; flex:1; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;"></span>
      <button id="chart-close-btn" style="background:none; border:1px solid #4a6899; color:#8baad4; font-size:13px; cursor:pointer; padding:3px 12px; border-radius:4px; flex-shrink:0;">닫기</button>
    </div>
    <div id="chart-plot" style="flex:1; min-height:0;"></div>
  </div>
</div>

<!-- ══ 외부 라이브러리 ══ -->
<script src="https://code.jquery.com/jquery-3.7.1.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/materialize/1.0.0/js/materialize.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/ag-grid-community@31.3.2/dist/ag-grid-community.min.noStyle.js"></script>
<script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>

{literal}
<script>

// ── 로딩 오버레이 ─────────────────────────────────────────
let _loadingDepth = 0;
function showLoading() {
  _loadingDepth++;
  document.getElementById('loading-overlay').style.display = 'flex';
}
function hideLoading() {
  if (--_loadingDepth <= 0) {
    _loadingDepth = 0;
    document.getElementById('loading-overlay').style.display = 'none';
  }
}


// ── 숫자 포매터 ──────────────────────────────────────────
const n = v => (v === null || v === undefined || v === '')
  ? ''
  : Number(v).toLocaleString();

const toNum = id => {
  const val = document.getElementById(id)?.value?.trim();
  return val === '' || val == null ? null : Number(val);
};


// ── AG-Grid 컬럼 정의 ────────────────────────────────────
const predictColDefs = [
  { field: 'data_cutoff', headerName: 'Date',   width: 108, sortable: true },
  { field: 'code',        headerName: 'Code',   width: 88,  sortable: true },
  { field: 'name',        headerName: 'Name',   flex: 1, minWidth: 120, sortable: true },
  {
    field:          'probability',
    headerName:     'Prob',
    width:          80,
    sortable:       true,
    sort:           'desc',
    valueFormatter: p => p.value != null ? Number(p.value).toFixed(4) : '',
  },
  { field: 'open',   headerName: 'Open',   width: 90,  valueFormatter: p => n(p.value) },
  { field: 'close',  headerName: 'Close',  width: 90,  valueFormatter: p => n(p.value) },
  { field: 'low',    headerName: 'Low',    width: 90,  valueFormatter: p => n(p.value) },
  { field: 'high',   headerName: 'High',   width: 90,  valueFormatter: p => n(p.value) },
  { field: 'volume', headerName: 'Volume', width: 110, valueFormatter: p => n(p.value) },
];

const scannerColDefs = [
  { field: 'date',            headerName: 'Date',      width: 108, sortable: true },
  { field: 'code',            headerName: 'Code',      width: 88,  sortable: true },
  { field: 'name',            headerName: 'Name',      flex: 1, minWidth: 130, sortable: true },
  { field: 'close',           headerName: 'Close',     width: 100, sortable: true,
    valueFormatter: p => n(p.value) },
  { field: 'upperband60_1',   headerName: 'UpperBand', width: 110, sortable: true,
    valueFormatter: p => n(p.value) },
  { field: 'upperband_ratio', headerName: 'Ratio',     width: 85,  sortable: true,
    valueFormatter: p => p.value != null ? Number(p.value).toFixed(4) : '' },
  { field: 'transAmnt',       headerName: 'TransAmnt', width: 130, sortable: true, sort: 'desc',
    valueFormatter: p => n(p.value) },
];


// ── 상태 변수 ────────────────────────────────────────────
// 숨겨진 패널의 그리드는 처음 해당 탭/패널이 열릴 때 지연 초기화
// (AG-Grid는 display:none 컨테이너에서 초기화하면 높이 0으로 렌더링됨)
let jpGrid              = null;
let krGrid              = null;
let scannerJpGrid       = null;
let scannerKrGrid       = null;
let jpWeeklyGrid        = null;
let krWeeklyGrid        = null;
let scannerJpWeeklyGrid = null;
let scannerKrWeeklyGrid = null;


// ── Predict 그리드 외부 필터 ─────────────────────────────
function makeRangeFilter(prefix) {
  return {
    isExternalFilterPresent: () => {
      return ['open-min', 'open-max', 'close-min', 'close-max']
        .some(k => toNum(`${prefix}-${k}`) !== null);
    },
    doesExternalFilterPass: node => {
      const d        = node.data;
      const openMin  = toNum(`${prefix}-open-min`);
      const openMax  = toNum(`${prefix}-open-max`);
      const closeMin = toNum(`${prefix}-close-min`);
      const closeMax = toNum(`${prefix}-close-max`);

      if (openMin  !== null && d.open  < openMin)  return false;
      if (openMax  !== null && d.open  > openMax)  return false;
      if (closeMin !== null && d.close < closeMin) return false;
      if (closeMax !== null && d.close > closeMax) return false;
      return true;
    },
  };
}


// ── AG-Grid 초기화 ────────────────────────────────────────
function createPredictGrid(elId, prefix, market, isWeekly) {
  const filter = makeRangeFilter(prefix);
  return agGrid.createGrid(document.getElementById(elId), {
    columnDefs:              predictColDefs,
    rowData:                 [],
    defaultColDef:           { resizable: true, suppressMovable: true },
    suppressCellFocus:       true,
    rowHeight:               30,
    headerHeight:            34,
    rowStyle:                { cursor: 'pointer' },
    isExternalFilterPresent: filter.isExternalFilterPresent,
    doesExternalFilterPass:  filter.doesExternalFilterPass,
    onRowClicked:            e => openChart(market, e.data.code, e.data.name, e.data.data_cutoff, isWeekly),
  });
}

function createScannerGrid(elId, market, isWeekly) {
  return agGrid.createGrid(document.getElementById(elId), {
    columnDefs:        scannerColDefs,
    rowData:           [],
    defaultColDef:     { resizable: true, suppressMovable: true },
    suppressCellFocus: true,
    rowHeight:         30,
    headerHeight:      34,
    rowStyle:          { cursor: 'pointer' },
    onRowClicked:      e => openChart(market, e.data.code, e.data.name, e.data.date, isWeekly),
  });
}


// ── 차트 열기 / 렌더링 ──────────────────────────────────
async function openChart(market, code, name, asOf, isWeekly) {
  const modal   = document.getElementById('chart-modal');
  const plotDiv = document.getElementById('chart-plot');
  document.getElementById('chart-title').textContent =
    `${code}  ${name || ''}  (${isWeekly ? '주봉' : '일봉'})  —  기준일: ${asOf}`;
  modal.style.display = 'flex';
  plotDiv.innerHTML = '';

  showLoading();
  try {
    const ep  = isWeekly ? '/api/series-weekly' : '/api/series';
    const res = await fetch(`${ep}?market=${encodeURIComponent(market)}&code=${encodeURIComponent(code)}&as_of=${encodeURIComponent(asOf)}`);
    const data = await res.json();
    renderChart('chart-plot', data.series || [], isWeekly);
  } catch (_) {
    plotDiv.innerHTML = '<div style="color:#e05c5c;padding:40px;text-align:center;font-size:13px">데이터 로드 실패</div>';
  } finally {
    hideLoading();
  }
}

function renderChart(divId, series, isWeekly) {
  if (!series.length) {
    document.getElementById(divId).innerHTML =
      '<div style="color:#8baad4;padding:40px;text-align:center;font-size:13px">데이터 없음</div>';
    return;
  }

  const dates = series.map(d => d.date);
  const maLine = (key, color, name) => ({
    type: 'scatter', mode: 'lines', x: dates, y: series.map(d => d[key]),
    name, line: { color, width: 1.2 }, hoverinfo: 'x+y',
  });

  const traces = [
    {
      type: 'candlestick',
      x: dates,
      open:  series.map(d => d.open),
      high:  series.map(d => d.high),
      low:   series.map(d => d.low),
      close: series.map(d => d.close),
      name: 'OHLC',
      increasing: { line: { color: '#e05c5c' } },
      decreasing: { line: { color: '#4a9adc' } },
    },
    maLine('ma5',  '#f0c040', 'MA5'),
    maLine('ma20', '#60d080', 'MA20'),
    maLine('ma60', '#e080c0', 'MA60'),
    {
      type: 'scatter', mode: 'lines', x: dates, y: series.map(d => d.bb_upper),
      name: 'BB上', line: { color: '#80b8ff', width: 1, dash: 'dot' }, hoverinfo: 'skip',
    },
    {
      type: 'scatter', mode: 'lines', x: dates, y: series.map(d => d.bb_lower),
      name: 'BB下', line: { color: '#80b8ff', width: 1, dash: 'dot' },
      fill: 'tonexty', fillcolor: 'rgba(128,184,255,0.06)', hoverinfo: 'skip',
    },
  ];

  if (!isWeekly) {
    traces.push(maLine('ma120', '#ffaa44', 'MA120'));
  }

  const layout = {
    paper_bgcolor: '#1e2a3a',
    plot_bgcolor:  '#1e2a3a',
    font:   { color: '#c9d8ef', size: 11 },
    xaxis:  { type: 'category', color: '#8baad4', rangeslider: { visible: false }, tickangle: -45, tickfont: { size: 10 } },
    yaxis:  { color: '#8baad4', gridcolor: '#2a3d52', automargin: true },
    legend: { orientation: 'h', y: 1.06, font: { size: 10 }, bgcolor: 'rgba(0,0,0,0)' },
    margin: { t: 4, r: 8, b: 50, l: 60 },
  };

  Plotly.newPlot(divId, traces, layout, { responsive: true, displayModeBar: false });
}


// ── Scanner 탭 전환 (JP / KR) ────────────────────────────
function initScannerTabs() {
  const tabBtns = document.querySelectorAll('.stab-btn');

  tabBtns.forEach(btn => {
    btn.addEventListener('click', async () => {
      tabBtns.forEach(b => b.classList.remove('active'));
      btn.classList.add('active');

      const targetId = btn.dataset.stab;
      document.querySelectorAll('.stab-panel').forEach(p => p.classList.remove('active'));
      document.getElementById(targetId).classList.add('active');

      if (targetId === 'stab-jp') {
        scannerJpGrid?.sizeColumnsToFit();
      }

      // KR 탭: 처음 열 때 지연 초기화 후 기본값 로드
      if (targetId === 'stab-kr') {
        if (!scannerKrGrid) {
          scannerKrGrid = createScannerGrid('scanner-grid-kr', 'KR', false);
          await Promise.all([
            loadDates('KR', 'scanner-kr-date', '/api/scanner-dates'),
            loadScannerDefaults('KR', 'scanner-kr-trans-amount', 'scanner-kr-close-max'),
          ]);
        } else {
          scannerKrGrid.sizeColumnsToFit();
        }
      }
    });
  });
}


// ── 날짜 목록 로드 ────────────────────────────────────────
async function loadDates(market, selectId, endpoint = '/api/predict-dates') {
  const res  = await fetch(`${endpoint}?market=${encodeURIComponent(market)}`);
  const data = await res.json();
  const sel  = document.getElementById(selectId);
  const dates = data.dates || [];

  sel.innerHTML = '';
  dates.forEach((date, idx) => {
    const opt       = document.createElement('option');
    opt.value       = date;
    opt.textContent = date;
    if (idx === 0) opt.selected = true;  // 첫 번째 항목 명시적 선택
    sel.appendChild(opt);
  });
  M.FormSelect.init(sel);

  return dates;
}


// ── select 값 읽기 (Materialize가 native select 값을 리셋할 수 있음) ─
function getSelectValue(selectId) {
  const sel = document.getElementById(selectId);
  // Materialize 초기화 후 .value가 빈값이 되는 경우 options[0]으로 폴백
  return sel?.value || sel?.options?.[0]?.value || '';
}


// ── Predict 검색 ─────────────────────────────────────────
async function searchPredicts(market, selectId, gridApi, endpoint = '/api/predict') {
  const asof = getSelectValue(selectId);
  if (!asof) return;

  showLoading();
  try {
    const res  = await fetch(`${endpoint}?market=${encodeURIComponent(market)}&as_of=${encodeURIComponent(asof)}`);
    const data = await res.json();
    gridApi.updateGridOptions({ rowData: data.rows || [] });
  } finally {
    hideLoading();
  }
}


// ── Predict 필터 초기화 ───────────────────────────────────
function clearPredictFilters(prefix, gridApi) {
  ['search', 'open-min', 'open-max', 'close-min', 'close-max'].forEach(k => {
    const el = document.getElementById(`${prefix}-${k}`);
    if (el) el.value = '';
  });
  M.updateTextFields();
  gridApi.updateGridOptions({ quickFilterText: '' });
  gridApi.onFilterChanged();
}


// ── 사이드바 내비게이션 ───────────────────────────────────
function initSidebarNav() {
  const menuItems = document.querySelectorAll('.side-menu li[data-panel]');

  menuItems.forEach(item => {
    item.addEventListener('click', async () => {
      menuItems.forEach(li => li.classList.remove('active'));
      item.classList.add('active');

      const targetId = item.dataset.panel;
      document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
      document.getElementById(targetId).classList.add('active');

      if (targetId === 'panel-predict') {
        const activePtab = document.querySelector('.ptab-panel.active');
        if (activePtab?.id === 'ptab-jp' && jpGrid) jpGrid.sizeColumnsToFit();
        if (activePtab?.id === 'ptab-kr' && krGrid) krGrid.sizeColumnsToFit();
      }

      if (targetId === 'panel-scanner') {
        if (!scannerJpGrid) {
          scannerJpGrid = createScannerGrid('scanner-grid-jp', 'JP', false);
          await Promise.all([
            loadDates('JP', 'scanner-jp-date', '/api/scanner-dates'),
            loadScannerDefaults('JP', 'scanner-jp-trans-amount', 'scanner-jp-close-max'),
          ]);
        } else {
          scannerJpGrid.sizeColumnsToFit();
        }
      }

      stopBatchLogPoller();
      if (targetId === 'panel-batch') {
        loadBatchTasks();
        loadBatchLogs();
      }

      if (targetId === 'panel-predict-weekly') {
        if (!jpWeeklyGrid) {
          jpWeeklyGrid = createPredictGrid('predict-grid-jp-w', 'jp-w', 'JP', true);
        } else {
          const activePtabW = document.querySelector('.ptab-w-panel.active');
          if (activePtabW?.id === 'ptab-w-jp') jpWeeklyGrid.sizeColumnsToFit();
          if (activePtabW?.id === 'ptab-w-kr' && krWeeklyGrid) krWeeklyGrid.sizeColumnsToFit();
        }
      }

      if (targetId === 'panel-scanner-weekly') {
        if (!scannerJpWeeklyGrid) {
          scannerJpWeeklyGrid = createScannerGrid('scanner-grid-jp-w', 'JP', true);
          await Promise.all([
            loadDates('JP', 'scanner-w-jp-date', '/api/scanner-weekly-dates'),
            loadScannerDefaults('JP', 'scanner-w-jp-trans-amount', 'scanner-w-jp-close-max', '/api/scanner-weekly-defaults'),
          ]);
        } else {
          scannerJpWeeklyGrid.sizeColumnsToFit();
        }
      }
    });
  });
}


// ── Predict 주봉 탭 전환 (JP / KR) ──────────────────────
function initPredictWeeklyTabs() {
  const tabBtns = document.querySelectorAll('.ptab-w-btn');

  tabBtns.forEach(btn => {
    btn.addEventListener('click', async () => {
      tabBtns.forEach(b => b.classList.remove('active'));
      btn.classList.add('active');

      const targetId = btn.dataset.ptabw;
      document.querySelectorAll('.ptab-w-panel').forEach(p => p.classList.remove('active'));
      document.getElementById(targetId).classList.add('active');

      if (targetId === 'ptab-w-jp') {
        jpWeeklyGrid?.sizeColumnsToFit();
      }

      if (targetId === 'ptab-w-kr') {
        if (!krWeeklyGrid) {
          krWeeklyGrid = createPredictGrid('predict-grid-kr-w', 'kr-w', 'KR', true);
        } else {
          krWeeklyGrid.sizeColumnsToFit();
        }
      }
    });
  });
}


// ── Scanner 주봉 탭 전환 (JP / KR) ──────────────────────
function initScannerWeeklyTabs() {
  const tabBtns = document.querySelectorAll('.stab-w-btn');

  tabBtns.forEach(btn => {
    btn.addEventListener('click', async () => {
      tabBtns.forEach(b => b.classList.remove('active'));
      btn.classList.add('active');

      const targetId = btn.dataset.stabw;
      document.querySelectorAll('.stab-w-panel').forEach(p => p.classList.remove('active'));
      document.getElementById(targetId).classList.add('active');

      if (targetId === 'stab-w-jp') {
        scannerJpWeeklyGrid?.sizeColumnsToFit();
      }

      if (targetId === 'stab-w-kr') {
        if (!scannerKrWeeklyGrid) {
          scannerKrWeeklyGrid = createScannerGrid('scanner-grid-kr-w', 'KR', true);
          await Promise.all([
            loadDates('KR', 'scanner-w-kr-date', '/api/scanner-weekly-dates'),
            loadScannerDefaults('KR', 'scanner-w-kr-trans-amount', 'scanner-w-kr-close-max', '/api/scanner-weekly-defaults'),
          ]);
        } else {
          scannerKrWeeklyGrid.sizeColumnsToFit();
        }
      }
    });
  });
}


// ── Predict 탭 전환 (JP / KR) ────────────────────────────
function initPredictTabs() {
  const tabBtns = document.querySelectorAll('.ptab-btn');

  tabBtns.forEach(btn => {
    btn.addEventListener('click', async () => {
      tabBtns.forEach(b => b.classList.remove('active'));
      btn.classList.add('active');

      const targetId = btn.dataset.ptab;
      document.querySelectorAll('.ptab-panel').forEach(p => p.classList.remove('active'));
      document.getElementById(targetId).classList.add('active');

      if (targetId === 'ptab-jp') {
        jpGrid?.sizeColumnsToFit();
      }

      if (targetId === 'ptab-kr') {
        if (!krGrid) {
          krGrid = createPredictGrid('predict-grid-kr', 'kr', 'KR', false);
        } else {
          krGrid.sizeColumnsToFit();
        }
      }
    });
  });
}


// ── 스캐너 기본값 로드 (trans_amnt_min / close_max) ──────
async function loadScannerDefaults(market, transId, closeId, endpoint = '/api/scanner-defaults') {
  showLoading();
  try {
    const res  = await fetch(`${endpoint}?market=${encodeURIComponent(market)}`);
    const data = await res.json();

    document.getElementById(transId).value = data.trans_amnt_min ?? '';
    document.getElementById(closeId).value = data.close_max ?? '';
    M.updateTextFields();
  } finally {
    hideLoading();
  }
}


// ── 스캐너 검색 ──────────────────────────────────────────
async function searchScanner(market, dateId, transId, closeId, gridApi, endpoint = '/api/scanner') {
  if (!gridApi) return;

  const date      = getSelectValue(dateId);
  const transAmnt = document.getElementById(transId).value.trim();
  const closeMax  = document.getElementById(closeId).value.trim();

  if (!date || !transAmnt || !closeMax) return;

  const params = new URLSearchParams({
    market,
    date,
    trans_amnt_min: transAmnt,
    close_max:      closeMax,
  });

  showLoading();
  try {
    const res  = await fetch(`${endpoint}?${params}`);
    const data = await res.json();
    gridApi.updateGridOptions({ rowData: data.rows || [] });
  } finally {
    hideLoading();
  }
}


// ── 초기화 ───────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', async () => {
  M.FormSelect.init(document.querySelectorAll('select'));
  initSidebarNav();
  initPredictTabs();
  initScannerTabs();
  initPredictWeeklyTabs();
  initScannerWeeklyTabs();
  initBatchPanel();

  // 차트 모달 닫기
  document.getElementById('chart-close-btn').addEventListener('click', () => {
    document.getElementById('chart-modal').style.display = 'none';
  });
  document.getElementById('chart-modal').addEventListener('click', e => {
    if (e.target === e.currentTarget) e.currentTarget.style.display = 'none';
  });

  // JP 그리드만 즉시 초기화 (JP 탭이 기본 활성)
  jpGrid = createPredictGrid('predict-grid-jp', 'jp', 'JP', false);

  showLoading();
  try {
    // 일봉/주봉 날짜 목록 병렬 로드
    await Promise.all([
      loadDates('JP', 'as-of-jp'),
      loadDates('KR', 'as-of-kr'),
      loadDates('JP', 'as-of-jp-w', '/api/predict-dates-weekly'),
      loadDates('KR', 'as-of-kr-w', '/api/predict-dates-weekly'),
    ]);
  } finally {
    hideLoading();
  }
});


// ── Batch Control ─────────────────────────────────────────
let batchLogPoller = null;
let selectedLogName = null;

async function runBatchTask(task) {
  const btn = document.querySelector(`.batch-run-btn[data-task="${task}"]`);
  const origText = btn?.textContent;
  if (btn) { btn.disabled = true; btn.textContent = '기동 중...'; }
  try {
    const res = await fetch('/api/batch/run', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ task }),
    });
    const data = await res.json();
    if (res.ok) {
      await Promise.all([loadBatchTasks(), loadBatchLogs()]);
      if (data.log_name) selectBatchLog(data.log_name);
    } else {
      alert(data.error || 'error');
    }
  } catch (_) {
    alert('Python 서비스에 연결할 수 없습니다.');
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = origText; }
  }
}

async function loadBatchTasks() {
  let tasks = [];
  try {
    const res = await fetch('/api/batch/tasks');
    const data = await res.json();
    tasks = data.tasks || [];
  } catch (_) {}
  const list = document.getElementById('batch-task-list');
  if (!tasks.length) {
    list.innerHTML = '<div style="color:#4a6899;font-size:13px;padding:4px 0">없음</div>';
    return;
  }
  list.innerHTML = tasks.map(t => {
    const cls = t.status === 'running' ? 'status-running'
              : t.exit_code === 0     ? 'status-success' : 'status-failed';
    const logBtn = t.log_name
      ? `<span class="batch-log-link" data-name="${t.log_name}" style="cursor:pointer;color:#1c7dff;font-size:11px;text-decoration:underline">${t.log_name}</span>`
      : '';
    return `<div class="batch-task-item">
      <span class="batch-task-name">${t.name}</span>
      <span class="${cls}">${t.status}</span>
      ${logBtn}
    </div>`;
  }).join('');
  list.querySelectorAll('.batch-log-link').forEach(el => {
    el.addEventListener('click', () => selectBatchLog(el.dataset.name));
  });
}

async function loadBatchLogs() {
  let logs = [];
  try {
    const res = await fetch('/api/batch/logs');
    const data = await res.json();
    logs = data.logs || [];
  } catch (_) {}
  const list = document.getElementById('batch-log-list');
  if (!logs.length) {
    list.innerHTML = '<div style="color:#4a6899;font-size:13px;padding:4px 0">없음</div>';
    return;
  }
  list.innerHTML = logs.map(l => {
    const dt = new Date(l.mtime * 1000).toLocaleString('ko-KR');
    const active = l.name === selectedLogName ? ' active' : '';
    return `<div class="batch-log-item${active}" data-name="${l.name}">${l.name} <span style="color:#4a6899">(${dt})</span></div>`;
  }).join('');
  list.querySelectorAll('.batch-log-item').forEach(el => {
    el.addEventListener('click', () => selectBatchLog(el.dataset.name));
  });
}

function selectBatchLog(name) {
  selectedLogName = name;
  const content = document.getElementById('batch-log-content');
  content.style.display = 'block';
  content.textContent = '';
  document.querySelectorAll('.batch-log-item').forEach(el =>
    el.classList.toggle('active', el.dataset.name === name)
  );
  stopBatchLogPoller();
  fetchBatchLog();
  batchLogPoller = setInterval(fetchBatchLog, 2000);
}

async function fetchBatchLog() {
  if (!selectedLogName) return;
  try {
    const res = await fetch(`/api/batch/log?name=${encodeURIComponent(selectedLogName)}`);
    if (!res.ok) return;
    const text = await res.text();
    const content = document.getElementById('batch-log-content');
    const atBottom = content.scrollTop + content.clientHeight >= content.scrollHeight - 10;
    content.textContent = text;
    if (atBottom) content.scrollTop = content.scrollHeight;
  } catch (_) {}
}

function stopBatchLogPoller() {
  if (batchLogPoller) { clearInterval(batchLogPoller); batchLogPoller = null; }
}

function initBatchPanel() {
  document.querySelectorAll('.batch-run-btn').forEach(btn => {
    btn.addEventListener('click', () => runBatchTask(btn.dataset.task));
  });
  document.getElementById('refresh-tasks').addEventListener('click', () => {
    loadBatchTasks();
    loadBatchLogs();
  });
}


// ── 이벤트 바인딩 ─────────────────────────────────────────

// Predict 검색 버튼
document.getElementById('predict-jp-btn')
  .addEventListener('click', () => searchPredicts('JP', 'as-of-jp', jpGrid));
document.getElementById('predict-kr-btn')
  .addEventListener('click', () => {
    if (krGrid) searchPredicts('KR', 'as-of-kr', krGrid);
  });

// Predict 필터 초기화 버튼
document.getElementById('jp-clear-btn')
  .addEventListener('click', () => { if (jpGrid) clearPredictFilters('jp', jpGrid); });
document.getElementById('kr-clear-btn')
  .addEventListener('click', () => { if (krGrid) clearPredictFilters('kr', krGrid); });

// Predict 텍스트 검색 (quickFilter)
document.getElementById('jp-search')
  .addEventListener('input', e => jpGrid?.updateGridOptions({ quickFilterText: e.target.value }));
document.getElementById('kr-search')
  .addEventListener('input', e => krGrid?.updateGridOptions({ quickFilterText: e.target.value }));

// Predict Open/Close 범위 필터 (입력 즉시 반영)
['jp-open-min', 'jp-open-max', 'jp-close-min', 'jp-close-max'].forEach(id => {
  document.getElementById(id).addEventListener('input', () => jpGrid?.onFilterChanged());
});
['kr-open-min', 'kr-open-max', 'kr-close-min', 'kr-close-max'].forEach(id => {
  document.getElementById(id).addEventListener('input', () => krGrid?.onFilterChanged());
});

// Scanner JP
document.getElementById('scanner-jp-btn')
  .addEventListener('click', () =>
    searchScanner('JP', 'scanner-jp-date', 'scanner-jp-trans-amount', 'scanner-jp-close-max', scannerJpGrid));

// Scanner KR
document.getElementById('scanner-kr-btn')
  .addEventListener('click', () =>
    searchScanner('KR', 'scanner-kr-date', 'scanner-kr-trans-amount', 'scanner-kr-close-max', scannerKrGrid));

// Predict 주봉 검색 버튼
document.getElementById('predict-jp-w-btn')
  .addEventListener('click', () => { if (jpWeeklyGrid) searchPredicts('JP', 'as-of-jp-w', jpWeeklyGrid, '/api/predict-weekly'); });
document.getElementById('predict-kr-w-btn')
  .addEventListener('click', () => { if (krWeeklyGrid) searchPredicts('KR', 'as-of-kr-w', krWeeklyGrid, '/api/predict-weekly'); });

// Predict 주봉 필터 초기화 버튼
document.getElementById('jp-w-clear-btn')
  .addEventListener('click', () => { if (jpWeeklyGrid) clearPredictFilters('jp-w', jpWeeklyGrid); });
document.getElementById('kr-w-clear-btn')
  .addEventListener('click', () => { if (krWeeklyGrid) clearPredictFilters('kr-w', krWeeklyGrid); });

// Predict 주봉 텍스트 검색
document.getElementById('jp-w-search')
  .addEventListener('input', e => jpWeeklyGrid?.updateGridOptions({ quickFilterText: e.target.value }));
document.getElementById('kr-w-search')
  .addEventListener('input', e => krWeeklyGrid?.updateGridOptions({ quickFilterText: e.target.value }));

// Predict 주봉 Open/Close 범위 필터
['jp-w-open-min', 'jp-w-open-max', 'jp-w-close-min', 'jp-w-close-max'].forEach(id => {
  document.getElementById(id).addEventListener('input', () => jpWeeklyGrid?.onFilterChanged());
});
['kr-w-open-min', 'kr-w-open-max', 'kr-w-close-min', 'kr-w-close-max'].forEach(id => {
  document.getElementById(id).addEventListener('input', () => krWeeklyGrid?.onFilterChanged());
});

// Scanner 주봉 JP
document.getElementById('scanner-w-jp-btn')
  .addEventListener('click', () =>
    searchScanner('JP', 'scanner-w-jp-date', 'scanner-w-jp-trans-amount', 'scanner-w-jp-close-max', scannerJpWeeklyGrid, '/api/scanner-weekly'));

// Scanner 주봉 KR
document.getElementById('scanner-w-kr-btn')
  .addEventListener('click', () =>
    searchScanner('KR', 'scanner-w-kr-date', 'scanner-w-kr-trans-amount', 'scanner-w-kr-close-max', scannerKrWeeklyGrid, '/api/scanner-weekly'));

</script>
{/literal}

</body>
</html>

