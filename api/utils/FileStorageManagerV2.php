<?php
class FileStorageManagerV2 {
    private $dataDir;
    private $cacheDir;
    private $publicDataDir;
    
    public function __construct() {
        $this->dataDir = DATA_DIR;
        $this->cacheDir = CACHE_DIR;
        $this->publicDataDir = defined('PUBLIC_DATA_DIR') ? PUBLIC_DATA_DIR : __DIR__ . '/../../public/data';
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
            $this->cacheDir . '/hardware-details',
            $this->publicDataDir . '/runs'
        ];
        
        foreach ($dirs as $dir) {
            if (!is_dir($dir)) {
                mkdir($dir, 0755, true);
            }
        }
    }
    
    /**
     * Store benchmark results using new run-based structure
     */
    public function storeBenchmarks($hardwareInfo, $benchmarkData, $runId = null) {
        $timestamp = time();
        
        // Generate run ID if not provided
        if (!$runId) {
            $runId = $timestamp . '_' . $this->generateHardwareSlug($hardwareInfo);
        }
        
        // Create run directory
        $runDir = $this->publicDataDir . '/runs/' . $runId;
        if (!is_dir($runDir)) {
            mkdir($runDir, 0755, true);
        }
        
        // Store individual benchmark files in run directory
        $benchmarkFiles = [];
        foreach ($benchmarkData as $type => $data) {
            $filename = $type . '.json';
            $filePath = $runDir . '/' . $filename;
            
            // Wrap data in appropriate envelope (support both 'data' and 'results')
            $benchmarkRecord = [
                'id' => $runId . '_' . $type,
                'type' => $type,
                'timestamp' => $timestamp,
                'data' => $data // Use 'data' envelope for consistency
            ];
            
            file_put_contents($filePath, json_encode($benchmarkRecord, JSON_PRETTY_PRINT));
            $benchmarkFiles[$type] = ['runs/' . $runId . '/' . $filename];
        }
        
        // Update or create hardware entries in index
        $this->updateIndex($hardwareInfo, $runId, $benchmarkFiles, $timestamp);
        
        // Store in old format for backward compatibility (optional)
        $this->storeBackwardCompatible($hardwareInfo, $benchmarkData, $runId);
        
        // Clear relevant caches
        $this->clearCache();
        
        return [
            'run_id' => $runId,
            'hardware_info' => $hardwareInfo,
            'benchmark_files' => $benchmarkFiles
        ];
    }
    
    /**
     * Generate hardware slug from hardware info
     */
    private function generateHardwareSlug($hardwareInfo) {
        $cpu = $hardwareInfo['cpu'] ?? 'unknown-cpu';
        $gpu = $hardwareInfo['gpu'] ?? '';
        
        // Normalize CPU name
        $cpuSlug = strtolower($cpu);
        $cpuSlug = preg_replace('/[^a-z0-9]+/', '-', $cpuSlug);
        $cpuSlug = trim($cpuSlug, '-');
        
        if ($gpu && $gpu !== 'Unknown') {
            // Normalize GPU name
            $gpuSlug = strtolower($gpu);
            $gpuSlug = preg_replace('/[^a-z0-9]+/', '-', $gpuSlug);
            $gpuSlug = trim($gpuSlug, '-');
            return $cpuSlug . '_' . $gpuSlug;
        }
        
        return $cpuSlug;
    }
    
    /**
     * Update the index.json file with new run information
     */
    private function updateIndex($hardwareInfo, $runId, $benchmarkFiles, $timestamp) {
        $indexFile = $this->publicDataDir . '/index.json';
        
        // Load existing index
        $index = [];
        if (file_exists($indexFile)) {
            $index = json_decode(file_get_contents($indexFile), true) ?: [];
        }
        
        // Initialize structure if needed
        if (!isset($index['hardware'])) {
            $index['hardware'] = ['cpus' => [], 'gpus' => []];
        }
        if (!isset($index['metadata'])) {
            $index['metadata'] = [
                'totalHardware' => 0,
                'totalRuns' => 0,
                'totalBenchmarks' => 0,
                'version' => '2.0',
                'benchmarkTypes' => ['7zip', 'reversan', 'llama', 'blender']
            ];
        }
        
        // Extract hardware identifiers
        $cpuId = $this->generateCpuId($hardwareInfo['cpu']);
        $gpuId = $this->generateGpuId($hardwareInfo['gpu']);
        
        // Create run entry
        $runEntry = [
            'runId' => $runId,
            'timestamp' => $timestamp,
            'benchmarks' => $benchmarkFiles
        ];
        
        // Update CPU entry
        $cpuEntry = $this->findOrCreateHardwareEntry($index['hardware']['cpus'], $cpuId, [
            'id' => $cpuId,
            'name' => $hardwareInfo['cpu'],
            'manufacturer' => $this->extractManufacturer($hardwareInfo['cpu']),
            'runs' => []
        ]);
        
        if ($gpuId !== 'unknown-gpu') {
            $runEntry['associatedGpu'] = $gpuId;
        }
        
        $cpuEntry['runs'][] = $runEntry;
        $cpuEntry['lastUpdated'] = $timestamp;
        
        // Update GPU entry if we have GPU info
        if ($gpuId !== 'unknown-gpu') {
            $gpuEntry = $this->findOrCreateHardwareEntry($index['hardware']['gpus'], $gpuId, [
                'id' => $gpuId,
                'name' => $hardwareInfo['gpu'],
                'manufacturer' => $this->extractManufacturer($hardwareInfo['gpu']),
                'framework' => $this->detectGpuFramework($hardwareInfo['gpu']),
                'runs' => []
            ]);
            
            // GPU only runs GPU-capable benchmarks
            $gpuBenchmarks = array_intersect_key($benchmarkFiles, array_flip(['llama', 'blender']));
            $gpuRunEntry = [
                'runId' => $runId,
                'timestamp' => $timestamp,
                'benchmarks' => $gpuBenchmarks,
                'associatedCpu' => $cpuId
            ];
            
            $gpuEntry['runs'][] = $gpuRunEntry;
            $gpuEntry['lastUpdated'] = $timestamp;
        }
        
        // Update metadata
        $index['metadata']['totalRuns'] = $this->countTotalRuns($index['hardware']);
        $index['metadata']['totalBenchmarks'] = $this->countTotalBenchmarks($index['hardware']);
        $index['metadata']['lastUpdated'] = $timestamp;
        
        // Save updated index
        file_put_contents($indexFile, json_encode($index, JSON_PRETTY_PRINT));
    }
    
    /**
     * Find existing hardware entry or create new one
     */
    private function findOrCreateHardwareEntry(&$hardwareList, $id, $template) {
        foreach ($hardwareList as &$entry) {
            if ($entry['id'] === $id) {
                return $entry;
            }
        }
        
        // Create new entry
        $hardwareList[] = $template;
        return end($hardwareList);
    }
    
    /**
     * Generate CPU ID from CPU name
     */
    private function generateCpuId($cpuName) {
        $id = strtolower($cpuName);
        $id = preg_replace('/[^a-z0-9]+/', '-', $id);
        return trim($id, '-');
    }
    
    /**
     * Generate GPU ID from GPU name
     */
    private function generateGpuId($gpuName) {
        if (!$gpuName || $gpuName === 'Unknown') {
            return 'unknown-gpu';
        }
        
        $id = strtolower($gpuName);
        $id = preg_replace('/[^a-z0-9]+/', '-', $id);
        return trim($id, '-');
    }
    
    /**
     * Extract manufacturer from hardware name
     */
    private function extractManufacturer($hardwareName) {
        $name = strtolower($hardwareName);
        if (strpos($name, 'amd') !== false) return 'AMD';
        if (strpos($name, 'intel') !== false) return 'Intel';
        if (strpos($name, 'nvidia') !== false) return 'NVIDIA';
        return 'Unknown';
    }
    
    /**
     * Detect GPU framework
     */
    private function detectGpuFramework($gpuName) {
        $name = strtolower($gpuName);
        if (strpos($name, 'radeon') !== false || strpos($name, 'amd') !== false) return 'HIP';
        if (strpos($name, 'nvidia') !== false || strpos($name, 'geforce') !== false || strpos($name, 'rtx') !== false) return 'CUDA';
        return 'Unknown';
    }
    
    /**
     * Count total runs across all hardware
     */
    private function countTotalRuns($hardware) {
        $count = 0;
        foreach (['cpus', 'gpus'] as $type) {
            if (isset($hardware[$type])) {
                foreach ($hardware[$type] as $hw) {
                    if (isset($hw['runs'])) {
                        $count += count($hw['runs']);
                    }
                }
            }
        }
        return $count;
    }
    
    /**
     * Count total benchmarks across all hardware
     */
    private function countTotalBenchmarks($hardware) {
        $count = 0;
        foreach (['cpus', 'gpus'] as $type) {
            if (isset($hardware[$type])) {
                foreach ($hardware[$type] as $hw) {
                    if (isset($hw['runs'])) {
                        foreach ($hw['runs'] as $run) {
                            if (isset($run['benchmarks'])) {
                                $count += count($run['benchmarks']);
                            }
                        }
                    }
                }
            }
        }
        return $count;
    }
    
    /**
     * Store in old format for backward compatibility
     */
    private function storeBackwardCompatible($hardwareInfo, $benchmarkData, $runId) {
        // This maintains the old API structure for existing clients
        $hardwareId = $runId; // Use runId as hardware ID for uniqueness
        
        // Store hardware info
        $hardwareFile = $this->dataDir . '/hardware/' . $hardwareId . '.json';
        file_put_contents($hardwareFile, json_encode($hardwareInfo, JSON_PRETTY_PRINT));
        
        // Store individual benchmark files
        foreach ($benchmarkData as $type => $data) {
            $benchmarkId = $hardwareId . '_' . $type . '_' . time();
            $benchmarkFile = $this->dataDir . '/benchmarks/' . $benchmarkId . '.json';
            
            $benchmarkRecord = [
                'id' => $benchmarkId,
                'type' => $type,
                'timestamp' => time(),
                'data' => $data
            ];
            
            file_put_contents($benchmarkFile, json_encode($benchmarkRecord, JSON_PRETTY_PRINT));
        }
        
        // Store aggregated results
        $resultsFile = $this->dataDir . '/results/' . $hardwareId . '.json';
        file_put_contents($resultsFile, json_encode($benchmarkData, JSON_PRETTY_PRINT));
    }
    
    /**
     * Clear cache
     */
    private function clearCache() {
        $cacheFiles = glob($this->cacheDir . '/*/*.json');
        foreach ($cacheFiles as $file) {
            unlink($file);
        }
    }
}
?>