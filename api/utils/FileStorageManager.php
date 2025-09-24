<?php
class FileStorageManager {
    private $dataDir;
    private $cacheDir;
    
    public function __construct() {
        $this->dataDir = DATA_DIR;
        $this->cacheDir = CACHE_DIR;
        $this->ensureDirectories();
    }
    
    /**
     * Ensure required directories exist
     */
    private function ensureDirectories() {
        $dirs = [
            $this->dataDir . '/hardware',
            $this->dataDir . '/benchmarks',
            $this->dataDir . '/results',
            $this->cacheDir . '/hardware-list',
            $this->cacheDir . '/hardware-details'
        ];
        
        foreach ($dirs as $dir) {
            if (!is_dir($dir)) {
                mkdir($dir, 0755, true);
            }
        }
    }
    
    /**
     * Store benchmark results and extract hardware info
     */
    public function storeBenchmarks($hardwareInfo, $benchmarkData) {
        $hardwareId = $hardwareInfo['id'];
        $timestamp = time();
        
        // Store hardware info
        $this->storeHardwareInfo($hardwareId, $hardwareInfo);
        
        // Store individual benchmark files
        $benchmarkIds = [];
        foreach ($benchmarkData as $type => $data) {
            $benchmarkId = $hardwareId . '_' . $type . '_' . $timestamp;
            $this->storeBenchmarkFile($benchmarkId, $type, $data);
            $benchmarkIds[$type] = $benchmarkId;
        }
        
        // Update aggregated results
        $this->updateAggregatedResults($hardwareId, $benchmarkData);
        
        // Clear relevant caches
        $this->clearCache();
        
        return [
            'hardware_id' => $hardwareId,
            'benchmark_ids' => $benchmarkIds
        ];
    }
    
    /**
     * Store hardware information
     */
    private function storeHardwareInfo($hardwareId, $hardwareInfo) {
        $file = $this->dataDir . '/hardware/' . $hardwareId . '.json';
        
        // Load existing data if it exists
        $existingData = [];
        if (file_exists($file)) {
            $existingData = json_decode(file_get_contents($file), true) ?: [];
        }
        
        // Merge with new data
        $mergedData = array_merge($existingData, $hardwareInfo);
        $mergedData['last_updated'] = time();
        
        file_put_contents($file, json_encode($mergedData, JSON_PRETTY_PRINT));
    }
    
    /**
     * Store individual benchmark file
     */
    private function storeBenchmarkFile($benchmarkId, $type, $data) {
        $file = $this->dataDir . '/benchmarks/' . $benchmarkId . '.json';
        
        $benchmarkRecord = [
            'id' => $benchmarkId,
            'type' => $type,
            'timestamp' => time(),
            'data' => $data
        ];
        
        file_put_contents($file, json_encode($benchmarkRecord, JSON_PRETTY_PRINT));
    }
    
    /**
     * Update aggregated results for a hardware
     */
    private function updateAggregatedResults($hardwareId, $benchmarkData) {
        $file = $this->dataDir . '/results/' . $hardwareId . '.json';
        
        // Load existing results
        $results = [];
        if (file_exists($file)) {
            $results = json_decode(file_get_contents($file), true) ?: [];
        }
        
        // Process each benchmark type
        foreach ($benchmarkData as $type => $data) {
            $results[$type] = $this->extractPerformanceMetrics($type, $data);
            $results[$type]['last_updated'] = time();
        }
        
        $results['summary'] = $this->generatePerformanceSummary($results);
        
        file_put_contents($file, json_encode($results, JSON_PRETTY_PRINT));
    }
    
    /**
     * Extract performance metrics from benchmark data
     */
    private function extractPerformanceMetrics($type, $data) {
        switch ($type) {
            case 'llama':
                return $this->extractLlamaMetrics($data);
            case '7zip':
                return $this->extract7zipMetrics($data);
            case 'reversan':
                return $this->extractReversanMetrics($data);
            case 'blender':
                return $this->extractBlenderMetrics($data);
            default:
                return ['raw_data' => $data];
        }
    }
    
    /**
     * Extract Llama performance metrics
     */
    private function extractLlamaMetrics($data) {
        $metrics = ['cpu' => [], 'gpu' => []];
        
        // CPU metrics
        if (isset($data['runs_cpu'])) {
            foreach ($data['runs_cpu'] as $run) {
                $metrics['cpu'][] = [
                    'tokens_per_second' => $run['metrics']['decode_tokens_per_second'] ?? 0,
                    'prompt_tokens_per_second' => $run['metrics']['prompt_tokens_per_second'] ?? 0,
                    'total_time_ms' => $run['metrics']['total_time_ms'] ?? 0
                ];
            }
        }
        
        // GPU metrics
        if (isset($data['runs_gpu'])) {
            foreach ($data['runs_gpu'] as $run) {
                $metrics['gpu'][] = [
                    'tokens_per_second' => $run['metrics']['decode_tokens_per_second'] ?? 0,
                    'prompt_tokens_per_second' => $run['metrics']['prompt_tokens_per_second'] ?? 0,
                    'total_time_ms' => $run['metrics']['total_time_ms'] ?? 0
                ];
            }
        }
        
        return $metrics;
    }
    
    /**
     * Extract 7zip performance metrics
     */
    private function extract7zipMetrics($data) {
        $metrics = [];
        
        if (isset($data['runs'])) {
            foreach ($data['runs'] as $run) {
                if ($run['success']) {
                    $metrics[] = [
                        'threads' => $run['threads'],
                        'elapsed_seconds' => $run['elapsed_seconds'],
                        'speedup' => $run['speedup'] ?? 1.0,
                        'thread_efficiency' => $run['thread_efficiency_percent'] ?? 100.0
                    ];
                }
            }
        }
        
        return ['thread_scaling' => $metrics];
    }
    
    /**
     * Extract Reversan performance metrics
     */
    private function extractReversanMetrics($data) {
        $metrics = [];
        
        if (isset($data['runs_threads'])) {
            foreach ($data['runs_threads'] as $run) {
                $metrics[] = [
                    'threads' => $run['config']['threads'],
                    'elapsed_time' => $run['metrics']['elapsed_time'],
                    'user_time' => $run['metrics']['user_time'],
                    'system_time' => $run['metrics']['system_time']
                ];
            }
        }
        
        return ['thread_performance' => $metrics];
    }
    
    /**
     * Extract Blender performance metrics
     */
    private function extractBlenderMetrics($data) {
        $metrics = [];
        
        if (isset($data['device_runs'])) {
            foreach ($data['device_runs'] as $run) {
                if ($run['success']) {
                    $deviceMetrics = [
                        'device_name' => $run['device_name'],
                        'device_framework' => $run['device_framework'],
                        'elapsed_seconds' => $run['elapsed_seconds'],
                        'total_score' => $run['total_score']
                    ];
                    
                    // Add scene-specific results if available
                    if (isset($run['scene_results'])) {
                        $deviceMetrics['scene_results'] = $run['scene_results'];
                    }
                    
                    $metrics[] = $deviceMetrics;
                }
            }
        }
        
        return ['device_performance' => $metrics];
    }
    
    /**
     * Generate performance summary
     */
    private function generatePerformanceSummary($results) {
        $summary = [
            'benchmark_count' => count($results) - 1, // Exclude summary itself
            'available_benchmarks' => array_keys(array_filter($results, fn($k) => $k !== 'summary', ARRAY_FILTER_USE_KEY)),
            'last_updated' => time()
        ];
        
        // Find best performance across benchmarks
        $bestPerformance = null;
        foreach ($results as $type => $data) {
            if ($type === 'summary') continue;
            
            switch ($type) {
                case 'llama':
                    if (isset($data['cpu']) && !empty($data['cpu'])) {
                        $maxTokens = max(array_column($data['cpu'], 'tokens_per_second'));
                        if (!$bestPerformance || $maxTokens > $bestPerformance['value']) {
                            $bestPerformance = [
                                'benchmark' => 'llama',
                                'value' => $maxTokens,
                                'unit' => 'tokens/s'
                            ];
                        }
                    }
                    break;
                case 'blender':
                    if (isset($data['device_performance']) && !empty($data['device_performance'])) {
                        $maxScore = max(array_column($data['device_performance'], 'total_score'));
                        if (!$bestPerformance || $maxScore > $bestPerformance['value']) {
                            $bestPerformance = [
                                'benchmark' => 'blender',
                                'value' => $maxScore,
                                'unit' => 'score'
                            ];
                        }
                    }
                    break;
            }
        }
        
        $summary['best_performance'] = $bestPerformance;
        
        return $summary;
    }
    
    /**
     * Get list of all hardware with summaries
     */
    public function getHardwareList() {
        $cacheFile = $this->cacheDir . '/hardware-list/list.json';
        
        // Check cache (5 minutes)
        if (file_exists($cacheFile) && (time() - filemtime($cacheFile)) < 300) {
            return json_decode(file_get_contents($cacheFile), true);
        }
        
        $cpus = [];
        $gpus = [];
        
        // Scan hardware directory
        $hardwareFiles = glob($this->dataDir . '/hardware/*.json');
        
        foreach ($hardwareFiles as $file) {
            $hardwareData = json_decode(file_get_contents($file), true);
            if (!$hardwareData) continue;
            
            $hardwareId = basename($file, '.json');
            
            // Load results
            $resultsFile = $this->dataDir . '/results/' . $hardwareId . '.json';
            $results = [];
            if (file_exists($resultsFile)) {
                $results = json_decode(file_get_contents($resultsFile), true) ?: [];
            }
            
            // Process CPUs and GPUs separately
            if (isset($hardwareData['cpus'])) {
                foreach ($hardwareData['cpus'] as $cpu) {
                    $cpus[] = $this->formatHardwareSummary($cpu, $results, $hardwareId);
                }
            }
            
            if (isset($hardwareData['gpus'])) {
                foreach ($hardwareData['gpus'] as $gpu) {
                    $gpus[] = $this->formatHardwareSummary($gpu, $results, $hardwareId);
                }
            }
        }
        
        $list = [
            'cpus' => $cpus,
            'gpus' => $gpus,
            'totalCount' => count($cpus) + count($gpus),
            'generated_at' => time()
        ];
        
        // Cache the result
        file_put_contents($cacheFile, json_encode($list, JSON_PRETTY_PRINT));
        
        return $list;
    }
    
    /**
     * Format hardware summary for listing
     */
    private function formatHardwareSummary($hardware, $results, $hardwareId) {
        $summary = [
            'hardware' => $hardware,
            'benchmarkCount' => isset($results['summary']) ? $results['summary']['benchmark_count'] : 0,
            'lastUpdated' => isset($results['summary']) ? date('Y-m-d', $results['summary']['last_updated']) : null,
            'bestPerformance' => isset($results['summary']) ? $results['summary']['best_performance'] : null,
            'averagePerformance' => []
        ];
        
        // Calculate average performance for each benchmark type
        foreach ($results as $type => $data) {
            if ($type === 'summary') continue;
            
            switch ($type) {
                case 'llama':
                    if (isset($data['cpu']) && !empty($data['cpu'])) {
                        $avgTokens = array_sum(array_column($data['cpu'], 'tokens_per_second')) / count($data['cpu']);
                        $summary['averagePerformance']['llama'] = round($avgTokens, 1);
                    }
                    break;
                case '7zip':
                    if (isset($data['thread_scaling']) && !empty($data['thread_scaling'])) {
                        $maxSpeedup = max(array_column($data['thread_scaling'], 'speedup'));
                        $summary['averagePerformance']['7zip'] = round($maxSpeedup, 2);
                    }
                    break;
                case 'blender':
                    if (isset($data['device_performance']) && !empty($data['device_performance'])) {
                        $avgScore = array_sum(array_column($data['device_performance'], 'total_score')) / count($data['device_performance']);
                        $summary['averagePerformance']['blender'] = round($avgScore, 1);
                    }
                    break;
            }
        }
        
        return $summary;
    }
    
    /**
     * Get detailed hardware information
     */
    public function getHardwareDetail($type, $id) {
        $cacheFile = $this->cacheDir . '/hardware-details/' . $type . '_' . $id . '.json';
        
        // Check cache (10 minutes)
        if (file_exists($cacheFile) && (time() - filemtime($cacheFile)) < 600) {
            return json_decode(file_get_contents($cacheFile), true);
        }
        
        // Find hardware by ID and type
        $hardwareFiles = glob($this->dataDir . '/hardware/*.json');
        $hardware = null;
        $hardwareId = null;
        
        foreach ($hardwareFiles as $file) {
            $data = json_decode(file_get_contents($file), true);
            if (!$data) continue;
            
            $fileId = basename($file, '.json');
            
            // Check CPUs
            if ($type === 'cpu' && isset($data['cpus'])) {
                foreach ($data['cpus'] as $cpu) {
                    if ($cpu['id'] === $id || strpos($fileId, $id) !== false) {
                        $hardware = $cpu;
                        $hardwareId = $fileId;
                        break 2;
                    }
                }
            }
            
            // Check GPUs
            if ($type === 'gpu' && isset($data['gpus'])) {
                foreach ($data['gpus'] as $gpu) {
                    if ($gpu['id'] === $id || strpos($fileId, $id) !== false) {
                        $hardware = $gpu;
                        $hardwareId = $fileId;
                        break 2;
                    }
                }
            }
        }
        
        if (!$hardware) {
            return null;
        }
        
        // Load results
        $resultsFile = $this->dataDir . '/results/' . $hardwareId . '.json';
        $results = [];
        if (file_exists($resultsFile)) {
            $results = json_decode(file_get_contents($resultsFile), true) ?: [];
        }
        
        // Load raw benchmark files
        $benchmarkFiles = glob($this->dataDir . '/benchmarks/' . $hardwareId . '_*.json');
        $benchmarks = [];
        foreach ($benchmarkFiles as $file) {
            $benchmark = json_decode(file_get_contents($file), true);
            if ($benchmark) {
                $benchmarks[] = $benchmark;
            }
        }
        
        $detail = [
            'hardware' => $hardware,
            'benchmarks' => $benchmarks,
            'results' => $results,
            'charts' => $this->generateChartData($hardware, $results)
        ];
        
        // Cache the result
        file_put_contents($cacheFile, json_encode($detail, JSON_PRETTY_PRINT));
        
        return $detail;
    }
    
    /**
     * Generate chart data for hardware
     */
    private function generateChartData($hardware, $results) {
        $charts = [];
        
        // Thread scaling chart for CPUs
        if ($hardware['type'] === 'cpu') {
            if (isset($results['7zip']['thread_scaling'])) {
                $data = $results['7zip']['thread_scaling'];
                $charts[] = [
                    'type' => 'line',
                    'title' => '7zip Thread Scaling Performance',
                    'xAxis' => [
                        'label' => 'Thread Count',
                        'data' => array_column($data, 'threads')
                    ],
                    'yAxis' => [
                        'label' => 'Speedup Factor',
                        'unit' => 'x'
                    ],
                    'series' => [{
                        'name' => 'Speedup',
                        'data' => array_column($data, 'speedup'),
                        'color' => '#007bff'
                    }]
                ];
            }
            
            if (isset($results['reversan']['thread_performance'])) {
                $data = $results['reversan']['thread_performance'];
                $charts[] = [
                    'type' => 'line',
                    'title' => 'Reversan Thread Performance',
                    'xAxis' => [
                        'label' => 'Thread Count',
                        'data' => array_column($data, 'threads')
                    ],
                    'yAxis' => [
                        'label' => 'Elapsed Time',
                        'unit' => 'seconds'
                    ],
                    'series' => [{
                        'name' => 'Execution Time',
                        'data' => array_column($data, 'elapsed_time'),
                        'color' => '#28a745'
                    }]
                ];
            }
        }
        
        // GPU performance charts
        if ($hardware['type'] === 'gpu') {
            if (isset($results['blender']['device_performance'])) {
                $data = $results['blender']['device_performance'];
                $charts[] = [
                    'type' => 'bar',
                    'title' => 'Blender Rendering Performance',
                    'xAxis' => [
                        'label' => 'Test Scenes',
                        'data' => ['Monster', 'Junkshop', 'Classroom'] // Common Blender benchmark scenes
                    ],
                    'yAxis' => [
                        'label' => 'Score',
                        'unit' => 'points'
                    ],
                    'series' => [{
                        'name' => 'Render Score',
                        'data' => array_column($data, 'total_score'),
                        'color' => '#ffc107'
                    }]
                ];
            }
        }
        
        return $charts;
    }
    
    /**
     * Clear all caches
     */
    public function clearCache() {
        $cacheFiles = glob($this->cacheDir . '/*/*.json');
        foreach ($cacheFiles as $file) {
            unlink($file);
        }
    }
}
?>