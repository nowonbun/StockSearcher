<?php

declare(strict_types=1);

namespace StockSearcher\WebApp;

use PDO;
use PDOException;
use RuntimeException;

final class App
{
    public function handle(): void
    {
        $path = parse_url($_SERVER['REQUEST_URI'] ?? '/', PHP_URL_PATH) ?: '/';
        $method = strtoupper($_SERVER['REQUEST_METHOD'] ?? 'GET');

        if ($method === 'POST' && $path === '/run') {
            $this->text('batch execution is disabled in php version', 501);
            return;
        }
        if ($method === 'GET' && $path === '/api/predict-dates') {
            $this->json(['dates' => $this->fetchPredictDates($this->market('KR'))]);
            return;
        }
        if ($method === 'GET' && $path === '/api/predict') {
            $market = $this->market('KR');
            $asOf = trim((string)($_GET['as_of'] ?? ''));
            if ($asOf === '') {
                $this->text('missing as_of', 400);
                return;
            }
            $this->json(['rows' => $this->fetchPredictions($market, $asOf)]);
            return;
        }
        if ($method === 'GET' && $path === '/api/scanner-dates') {
            $this->json(['dates' => $this->fetchScannerDates($this->market('JP'))]);
            return;
        }
        if ($method === 'GET' && $path === '/api/scanner-weekly-dates') {
            $this->json(['dates' => $this->fetchScannerWeeklyDates($this->market('JP'))]);
            return;
        }
        if ($method === 'GET' && $path === '/api/scanner-defaults') {
            $this->json($this->scannerDefaults($this->market('JP')));
            return;
        }
        if ($method === 'GET' && $path === '/api/predict-dates-weekly') {
            $this->json(['dates' => $this->fetchPredictDatesWeekly($this->market('KR'))]);
            return;
        }
        if ($method === 'GET' && $path === '/api/predict-weekly') {
            $market = $this->market('KR');
            $asOf = trim((string)($_GET['as_of'] ?? ''));
            if ($asOf === '') {
                $this->text('missing as_of', 400);
                return;
            }
            $this->json(['rows' => $this->fetchPredictionsWeekly($market, $asOf)]);
            return;
        }
        if ($method === 'GET' && $path === '/api/scanner-weekly-defaults') {
            $this->json($this->scannerWeeklyDefaults($this->market('JP')));
            return;
        }
        if ($method === 'GET' && $path === '/api/scanner-weekly') {
            $market = $this->market('JP');
            $date = trim((string)($_GET['date'] ?? ''));
            $trans = trim((string)($_GET['trans_amnt_min'] ?? ''));
            $closeMax = trim((string)($_GET['close_max'] ?? ''));
            if ($date === '' || $trans === '' || $closeMax === '') {
                $this->text('missing date/trans_amnt_min/close_max', 400);
                return;
            }
            $this->json(['rows' => $this->fetchUpperbandBreakoutsWeekly($market, $date, (float)$trans, (float)$closeMax)]);
            return;
        }
        if ($method === 'GET' && $path === '/api/scanner') {
            $market = $this->market('JP');
            $date = trim((string)($_GET['date'] ?? ''));
            $trans = trim((string)($_GET['trans_amnt_min'] ?? ''));
            $closeMax = trim((string)($_GET['close_max'] ?? ''));
            if ($date === '' || $trans === '' || $closeMax === '') {
                $this->text('missing date/trans_amnt_min/close_max', 400);
                return;
            }
            $this->json(['rows' => $this->fetchUpperbandBreakouts($market, $date, (float)$trans, (float)$closeMax)]);
            return;
        }
        if ($method === 'GET' && $path === '/api/series') {
            $market = $this->market('KR');
            $code = trim((string)($_GET['code'] ?? ''));
            $asOf = trim((string)($_GET['as_of'] ?? ''));
            if ($code === '' || $asOf === '') {
                $this->text('missing code/as_of', 400);
                return;
            }
            $this->json(['series' => $this->fetchSeries($market, $code, $asOf, 240)]);
            return;
        }
        if ($method === 'GET' && $path === '/api/series-weekly') {
            $market = $this->market('KR');
            $code = trim((string)($_GET['code'] ?? ''));
            $asOf = trim((string)($_GET['as_of'] ?? ''));
            if ($code === '' || $asOf === '') {
                $this->text('missing code/as_of', 400);
                return;
            }
            $this->json(['series' => $this->fetchWeeklySeries($market, $code, $asOf, 120)]);
            return;
        }
        if ($method === 'POST' && $path === '/api/batch/run') {
            $body = (string)file_get_contents('php://input');
            [$status, $payload] = $this->pythonRequest('POST', '/api/run', $body);
            http_response_code($status);
            header('Content-Type: application/json; charset=utf-8');
            echo $payload;
            return;
        }
        if ($method === 'GET' && $path === '/api/batch/tasks') {
            [$status, $payload] = $this->pythonRequest('GET', '/api/tasks');
            http_response_code($status);
            header('Content-Type: application/json; charset=utf-8');
            echo $payload;
            return;
        }
        if ($method === 'GET' && $path === '/api/batch/logs') {
            $this->json(['logs' => $this->listLogs()]);
            return;
        }
        if ($method === 'GET' && $path === '/api/batch/log') {
            $name = trim((string)($_GET['name'] ?? ''));
            $content = $this->readLogTail($name);
            if ($content === null) {
                $this->text('not found', 404);
                return;
            }
            http_response_code(200);
            header('Content-Type: text/plain; charset=utf-8');
            echo $content;
            return;
        }
        if (str_starts_with($path, '/mcp')) {
            $this->text('mcp endpoint is not implemented in php version', 501);
            return;
        }
        if ($method === 'GET' && $path === '/') {
            $this->index();
            return;
        }

        $this->text('not found', 404);
    }

    private function market(string $default): string
    {
        $market = strtoupper(trim((string)($_GET['market'] ?? $default)));
        if (!in_array($market, ['KR', 'JP'], true)) {
            $this->text('invalid market', 400);
            exit;
        }
        return $market;
    }

    private function index(): void
    {
        $msg = (string)($_GET['msg'] ?? '');
        $smarty = require __DIR__ . '/bootstrap.php';
        $smarty->assign('message', $msg);
        $smarty->display('index.tpl');
    }

    private function pdo(string $market): PDO
    {
        $iniPath = '/app/config.ini';
        if (!is_file($iniPath)) {
            $iniPath = dirname(__DIR__) . '/config.ini';
        }
        if (!is_file($iniPath)) {
            $iniPath = dirname(__DIR__, 2) . '/config.ini';
        }
        $ini = parse_ini_file($iniPath, true, INI_SCANNER_TYPED);
        if (!is_array($ini) || !isset($ini['database'])) {
            throw new RuntimeException('config.ini parse failed');
        }
        $db = $ini['database'];
        $dbname = $market === 'JP' ? ($db['database_jp'] ?? null) : ($db['database_kr'] ?? null);
        if (!$dbname) {
            throw new RuntimeException('database not configured');
        }
        $host = (string)($db['host'] ?? '127.0.0.1');
        $port = (int)($db['port'] ?? 3306);
        $user = (string)($db['user'] ?? '');
        $password = (string)($db['password'] ?? '');
        $dsn = "mysql:host={$host};port={$port};dbname={$dbname};charset=utf8mb4";
        try {
            return new PDO($dsn, $user, $password, [
                PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION,
                PDO::ATTR_DEFAULT_FETCH_MODE => PDO::FETCH_ASSOC,
            ]);
        } catch (PDOException $e) {
            throw new RuntimeException('db connect failed: ' . $e->getMessage());
        }
    }

    private function etfFilter(string $market, string $alias = 'l'): string
    {
        return $market === 'JP' ? " AND {$alias}.stocktype != 'ETF・ETN'" : '';
    }

    private function predictTable(string $market): string { return $market === 'JP' ? 'STOCK_PREDICT_JP' : 'STOCK_PREDICT_KR'; }
    private function dataTable(string $market): string { return $market === 'JP' ? 'STOCK_DATA_JP' : 'STOCK_DATA_KR'; }
    private function listTable(string $market): string { return $market === 'JP' ? 'STOCK_LIST_JP' : 'STOCK_LIST_KR'; }
    private function weeklyPredictTable(string $market): string { return $market === 'JP' ? 'STOCK_PREDICT_WEEK_JP' : 'STOCK_PREDICT_WEEK_KR'; }
    private function weeklyDataTable(string $market): string { return $market === 'JP' ? 'STOCK_DATA_WEEK_JP' : 'STOCK_DATA_WEEK_KR'; }

    private function fetchPredictDates(string $market, int $limit = 120): array
    {
        $pdo = $this->pdo($market);
        $sql = "SELECT DISTINCT data_cutoff FROM {$this->predictTable($market)} ORDER BY data_cutoff DESC LIMIT :limit";
        $st = $pdo->prepare($sql);
        $st->bindValue(':limit', $limit, PDO::PARAM_INT);
        $st->execute();
        return array_map(static fn(array $r): string => substr((string)$r['data_cutoff'], 0, 10), $st->fetchAll());
    }

    private function fetchPredictions(string $market, string $asOf): array
    {
        $pdo = $this->pdo($market);
        $sql = "
            SELECT p.data_cutoff,p.code,l.name,p.probability,d.Open,d.Close,d.Low,d.High,d.Volume
            FROM {$this->predictTable($market)} p
            JOIN {$this->listTable($market)} l ON l.code = p.code
            JOIN {$this->dataTable($market)} d ON d.code = p.code AND d.date = :as_of2
            WHERE p.data_cutoff = :as_of{$this->etfFilter($market)}
            ORDER BY p.probability DESC
        ";
        $st = $pdo->prepare($sql);
        $st->execute([':as_of' => $asOf, ':as_of2' => $asOf]);
        $rows = [];
        foreach ($st->fetchAll() as $r) {
            $rows[] = [
                'data_cutoff' => substr((string)$r['data_cutoff'], 0, 10),
                'code' => $r['code'], 'name' => $r['name'], 'probability' => (float)$r['probability'],
                'open' => $this->num($r['Open']), 'close' => $this->num($r['Close']), 'low' => $this->num($r['Low']),
                'high' => $this->num($r['High']), 'volume' => $this->num($r['Volume']),
            ];
        }
        return $rows;
    }

    private function previousTradingDate(string $market): ?string
    {
        $pdo = $this->pdo($market);
        $sql = "SELECT DISTINCT date FROM {$this->dataTable($market)} WHERE date >= DATE_SUB(CURDATE(), INTERVAL 30 DAY) ORDER BY date DESC LIMIT 30";
        $rows = $pdo->query($sql)->fetchAll();
        if (count($rows) >= 2) return substr((string)$rows[1]['date'], 0, 10);
        if (count($rows) === 1) return substr((string)$rows[0]['date'], 0, 10);
        return null;
    }

    // 날짜 목록 조회 기준 종목 (JP: 도요타 7203, KR: 삼성전자 005930)
    private function anchorCode(string $market): string
    {
        return $market === 'JP' ? '7203' : '005930';
    }

    private function fetchScannerDates(string $market, int $limit = 120): array
    {
        $pdo = $this->pdo($market);
        $sql = "SELECT date FROM {$this->dataTable($market)} WHERE code = :code ORDER BY date DESC LIMIT :limit";
        $st = $pdo->prepare($sql);
        $st->bindValue(':code', $this->anchorCode($market));
        $st->bindValue(':limit', $limit, PDO::PARAM_INT);
        $st->execute();
        return array_map(static fn(array $r): string => substr((string)$r['date'], 0, 10), $st->fetchAll());
    }

    private function fetchScannerWeeklyDates(string $market, int $limit = 120): array
    {
        $pdo = $this->pdo($market);
        $sql = "SELECT date FROM {$this->weeklyDataTable($market)} WHERE code = :code ORDER BY date DESC LIMIT :limit";
        $st = $pdo->prepare($sql);
        $st->bindValue(':code', $this->anchorCode($market));
        $st->bindValue(':limit', $limit, PDO::PARAM_INT);
        $st->execute();
        return array_map(static fn(array $r): string => substr((string)$r['date'], 0, 10), $st->fetchAll());
    }

    private function scannerDefaults(string $market): array
    {
        if ($market === 'JP') {
            return ['date' => $this->previousTradingDate($market), 'close_max' => 1000, 'trans_amnt_min' => 500000000];
        }
        return ['date' => $this->previousTradingDate($market), 'close_max' => 100000, 'trans_amnt_min' => 1000000000];
    }

    private function fetchPredictDatesWeekly(string $market, int $limit = 120): array
    {
        $pdo = $this->pdo($market);
        $sql = "SELECT DISTINCT data_cutoff FROM {$this->weeklyPredictTable($market)} ORDER BY data_cutoff DESC LIMIT :limit";
        $st = $pdo->prepare($sql);
        $st->bindValue(':limit', $limit, PDO::PARAM_INT);
        $st->execute();
        return array_map(static fn(array $r): string => substr((string)$r['data_cutoff'], 0, 10), $st->fetchAll());
    }

    private function fetchPredictionsWeekly(string $market, string $asOf): array
    {
        $pdo = $this->pdo($market);
        $sql = "
            SELECT p.data_cutoff,p.code,l.name,p.probability,d.Open,d.Close,d.Low,d.High,d.Volume
            FROM {$this->weeklyPredictTable($market)} p
            JOIN {$this->listTable($market)} l ON l.code = p.code
            LEFT JOIN {$this->weeklyDataTable($market)} d ON d.code = p.code AND d.date = (
                SELECT MAX(date) FROM {$this->weeklyDataTable($market)} WHERE date <= :as_of2
            )
            WHERE p.data_cutoff = :as_of{$this->etfFilter($market)}
            ORDER BY p.probability DESC
        ";
        $st = $pdo->prepare($sql);
        $st->execute([':as_of' => $asOf, ':as_of2' => $asOf]);
        $rows = [];
        foreach ($st->fetchAll() as $r) {
            $rows[] = [
                'data_cutoff' => substr((string)$r['data_cutoff'], 0, 10),
                'code' => $r['code'], 'name' => $r['name'], 'probability' => (float)$r['probability'],
                'open' => $this->num($r['Open']), 'close' => $this->num($r['Close']), 'low' => $this->num($r['Low']),
                'high' => $this->num($r['High']), 'volume' => $this->num($r['Volume']),
            ];
        }
        return $rows;
    }

    private function previousWeeklyDate(string $market): ?string
    {
        $pdo = $this->pdo($market);
        $sql = "SELECT DISTINCT date FROM {$this->weeklyDataTable($market)} WHERE date >= DATE_SUB(CURDATE(), INTERVAL 30 DAY) ORDER BY date DESC LIMIT 30";
        $rows = $pdo->query($sql)->fetchAll();
        if (count($rows) >= 2) return substr((string)$rows[1]['date'], 0, 10);
        if (count($rows) === 1) return substr((string)$rows[0]['date'], 0, 10);
        return null;
    }

    private function scannerWeeklyDefaults(string $market): array
    {
        if ($market === 'JP') {
            return ['date' => $this->previousWeeklyDate($market), 'close_max' => 1000, 'trans_amnt_min' => 2500000000];
        }
        return ['date' => $this->previousWeeklyDate($market), 'close_max' => 100000, 'trans_amnt_min' => 5000000000];
    }

    private function fetchUpperbandBreakoutsWeekly(string $market, string $scanDate, float $trans, float $closeMax): array
    {
        $pdo = $this->pdo($market);
        $sql = "
            SELECT sd.date,sd.code,sl.name,sd.Close,sd.UpperBand60_1,sd.TransAmnt AS transAmnt,(sd.Close/NULLIF(sd.UpperBand60_1,0)) AS upperband_ratio
            FROM {$this->weeklyDataTable($market)} sd
            JOIN {$this->listTable($market)} sl ON sl.code = sd.code
            WHERE sd.date=:d AND sd.Close > sd.UpperBand60_1
              AND sd.TransAmnt > :t AND sd.Close < :c{$this->etfFilter($market, 'sl')}
            ORDER BY sd.TransAmnt DESC
        ";
        $st = $pdo->prepare($sql);
        $st->execute([':d' => $scanDate, ':t' => $trans, ':c' => $closeMax]);
        $rows = [];
        foreach ($st->fetchAll() as $r) {
            $rows[] = [
                'date' => substr((string)$r['date'], 0, 10), 'code' => $r['code'], 'name' => $r['name'],
                'close' => $this->num($r['Close']), 'upperband60_1' => $this->num($r['UpperBand60_1']),
                'transAmnt' => $this->num($r['transAmnt']), 'upperband_ratio' => $this->num($r['upperband_ratio']),
            ];
        }
        return $rows;
    }

    private function fetchUpperbandBreakouts(string $market, string $scanDate, float $trans, float $closeMax): array
    {
        $pdo = $this->pdo($market);
        $sql = "
            SELECT sd.date,sd.code,sl.name,sd.Close,sd.UpperBand60_1,sd.transAmnt,(sd.Close/NULLIF(sd.UpperBand60_1,0)) AS upperband_ratio
            FROM {$this->dataTable($market)} sd
            JOIN {$this->listTable($market)} sl ON sl.code = sd.code
            WHERE sd.date=:d AND sd.Close > sd.UpperBand60_1
              AND sd.transAmnt > :t AND sd.Close < :c{$this->etfFilter($market, 'sl')}
            ORDER BY sd.transAmnt DESC
        ";
        $st = $pdo->prepare($sql);
        $st->execute([':d' => $scanDate, ':t' => $trans, ':c' => $closeMax]);
        $rows = [];
        foreach ($st->fetchAll() as $r) {
            $rows[] = [
                'date' => substr((string)$r['date'], 0, 10), 'code' => $r['code'], 'name' => $r['name'],
                'close' => $this->num($r['Close']), 'upperband60_1' => $this->num($r['UpperBand60_1']),
                'transAmnt' => $this->num($r['transAmnt']), 'upperband_ratio' => $this->num($r['upperband_ratio']),
            ];
        }
        return $rows;
    }

    private function fetchSeries(string $market, string $code, string $asOf, int $limit): array
    {
        $pdo = $this->pdo($market);
        $sql = "
            SELECT date,Open,High,Low,Close,Volume,`5MvAvg`,`20MvAvg`,`60MvAvg`,`120MvAvg`,`240MvAvg`,
                   UpperBand60_1,LowerBand60_1,LowerBand60_3,DI_plus,DI_minus,ADX
            FROM {$this->dataTable($market)}
            WHERE code=:code AND date<=:as_of
            ORDER BY date DESC LIMIT :limit
        ";
        $st = $pdo->prepare($sql);
        $st->bindValue(':code', $code);
        $st->bindValue(':as_of', $asOf);
        $st->bindValue(':limit', $limit, PDO::PARAM_INT);
        $st->execute();
        $desc = $st->fetchAll();
        $desc = array_reverse($desc);
        $rows = [];
        foreach ($desc as $r) {
            $rows[] = [
                'date' => substr((string)$r['date'], 0, 10), 'open' => $this->num($r['Open']), 'high' => $this->num($r['High']),
                'low' => $this->num($r['Low']), 'close' => $this->num($r['Close']), 'volume' => $this->num($r['Volume']),
                'ma5' => $this->num($r['5MvAvg']), 'ma20' => $this->num($r['20MvAvg']), 'ma60' => $this->num($r['60MvAvg']),
                'ma120' => $this->num($r['120MvAvg']), 'ma240' => $this->num($r['240MvAvg']),
                'bb_upper' => $this->num($r['UpperBand60_1']), 'bb_lower' => $this->num($r['LowerBand60_1']), 'bb_lower3' => $this->num($r['LowerBand60_3']),
                'di_plus' => $this->num($r['DI_plus']), 'di_minus' => $this->num($r['DI_minus']), 'adx' => $this->num($r['ADX']),
            ];
        }
        return $rows;
    }

    private function fetchWeeklySeries(string $market, string $code, string $asOf, int $limit): array
    {
        $pdo = $this->pdo($market);
        $sql = "
            SELECT date,Open,High,Low,Close,Volume,`5MvAvg`,`20MvAvg`,`60MvAvg`,
                   UpperBand60_1,LowerBand60_1,LowerBand60_3,DI_plus,DI_minus,ADX
            FROM {$this->weeklyDataTable($market)}
            WHERE code=:code AND date<=:as_of
            ORDER BY date DESC LIMIT :limit
        ";
        $st = $pdo->prepare($sql);
        $st->bindValue(':code', $code);
        $st->bindValue(':as_of', $asOf);
        $st->bindValue(':limit', $limit, PDO::PARAM_INT);
        $st->execute();
        $desc = $st->fetchAll();
        $desc = array_reverse($desc);
        $rows = [];
        foreach ($desc as $r) {
            $rows[] = [
                'date' => substr((string)$r['date'], 0, 10), 'open' => $this->num($r['Open']), 'high' => $this->num($r['High']),
                'low' => $this->num($r['Low']), 'close' => $this->num($r['Close']), 'volume' => $this->num($r['Volume']),
                'ma5' => $this->num($r['5MvAvg']), 'ma20' => $this->num($r['20MvAvg']), 'ma60' => $this->num($r['60MvAvg']),
                'bb_upper' => $this->num($r['UpperBand60_1']), 'bb_lower' => $this->num($r['LowerBand60_1']), 'bb_lower3' => $this->num($r['LowerBand60_3']),
                'di_plus' => $this->num($r['DI_plus']), 'di_minus' => $this->num($r['DI_minus']), 'adx' => $this->num($r['ADX']),
            ];
        }
        return $rows;
    }

    private function pythonApiUrl(): string
    {
        return rtrim((string)(getenv('PYTHON_API_URL') ?: 'http://stocksearcher:9999'), '/');
    }

    private function pythonRequest(string $method, string $endpoint, string $body = ''): array
    {
        $url = $this->pythonApiUrl() . $endpoint;
        $opts = ['method' => $method, 'timeout' => 15, 'ignore_errors' => true];
        if ($body !== '') {
            $opts['header'] = 'Content-Type: application/json';
            $opts['content'] = $body;
        }
        $ctx = stream_context_create(['http' => $opts]);
        $resp = @file_get_contents($url, false, $ctx);
        if ($resp === false) {
            return [503, '{"error":"python service unavailable"}'];
        }
        $status = 200;
        foreach ($http_response_header ?? [] as $h) {
            if (preg_match('/^HTTP\/\S+\s+(\d+)/', $h, $m)) {
                $status = (int)$m[1];
                break;
            }
        }
        return [$status, $resp];
    }

    private function logDir(): string
    {
        return rtrim((string)(getenv('LOG_DIR') ?: '/data/log'), '/');
    }

    private function listLogs(): array
    {
        $dir = $this->logDir();
        if (!is_dir($dir)) return [];
        $files = glob($dir . '/*.log') ?: [];
        usort($files, static fn($a, $b) => filemtime($b) - filemtime($a));
        $result = [];
        foreach (array_slice($files, 0, 50) as $f) {
            $result[] = ['name' => basename($f), 'mtime' => filemtime($f)];
        }
        return $result;
    }

    private function readLogTail(string $name): ?string
    {
        if ($name === '' || str_contains($name, '/') || str_contains($name, '\\') || str_starts_with($name, '.')) {
            return null;
        }
        $path = $this->logDir() . '/' . $name;
        if (!is_file($path)) return null;
        $fh = fopen($path, 'rb');
        if ($fh === false) return null;
        fseek($fh, 0, SEEK_END);
        $size = ftell($fh);
        $start = max(0, $size - 20000);
        fseek($fh, $start);
        $content = (string)fread($fh, $size);
        fclose($fh);
        if ($start > 0) {
            $nl = strpos($content, "\n");
            if ($nl !== false) $content = substr($content, $nl + 1);
        }
        return $content;
    }

    private function num(mixed $v): ?float
    {
        if ($v === null || $v === '') return null;
        return (float)$v;
    }

    private function json(array $payload, int $status = 200): void
    {
        http_response_code($status);
        header('Content-Type: application/json; charset=utf-8');
        echo json_encode($payload, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES);
    }

    private function text(string $text, int $status = 200): void
    {
        http_response_code($status);
        header('Content-Type: text/plain; charset=utf-8');
        echo $text;
    }
}
