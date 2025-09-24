<?php
class SimpleStorageManager {
    private $dataDir;
    
    public function __construct() {
        // Always use public/data directory for the main data structure
        $this->dataDir = defined('PUBLIC_DATA_DIR') ? PUBLIC_DATA_DIR : __DIR__ . '/../../public/data';
        $this->ensureDirectories();
    }
    
    /**
     * Ensure required directories exist
     */
    private function ensureDirectories() {
        $dirs = [
            $this->dataDir,
            $this->dataDir . '/uploads'
        ];
        
        foreach ($dirs as $dir) {
            if (!is_dir($dir)) {
                mkdir($dir, 0755, true);
            }
        }
    }
    
    /**
     * Store benchmark results using simple upload folder structure
     */
    public function storeBenchmarks($hardwareInfo, $benchmarkData, $runId = null) {
        $timestamp = time();
        
        // Generate run ID if not provided (date_nth_upload format)
        if (!$runId) {
            $runId = $this->generateRunId($timestamp);
        }
        
        // Create upload directory
        $uploadDir = $this->dataDir . '/uploads/' . $runId;
        if (!is_dir($uploadDir)) {
            mkdir($uploadDir, 0755, true);
        }
        
        // Store individual benchmark files in upload directory
        $benchmarkFiles = [];
        foreach ($benchmarkData as $type => $data) {
            $filename = $type . '.json';
            $filepath = $uploadDir . '/' . $filename;
            
            file_put_contents($filepath, json_encode($data, JSON_PRETTY_PRINT));
            $benchmarkFiles[$type] = 'uploads/' . $runId . '/' . $filename;
        }
        
        // Store hardware info
        $hardwareFile = $uploadDir . '/hardware_info.json';
        file_put_contents($hardwareFile, json_encode($hardwareInfo, JSON_PRETTY_PRINT));
        
        return [
            'run_id' => $runId,
            'upload_dir' => $uploadDir,
            'files_stored' => array_keys($benchmarkFiles)
        ];
    }
    
    /**
     * Generate a run ID based on timestamp and existing uploads
     * Format: YYYYMMDD_HHMMSS_N (where N is incremental if multiple uploads in same second)
     */
    private function generateRunId($timestamp) {
        $datetime = date('Ymd_His', $timestamp);
        $uploadsDir = $this->dataDir . '/uploads';
        
        // Check if this exact timestamp already exists
        $baseId = $datetime;
        $count = 1;
        
        while (is_dir($uploadsDir . '/' . $baseId . ($count > 1 ? '_' . $count : ''))) {
            $count++;
        }
        
        return $baseId . ($count > 1 ? '_' . $count : '');
    }
    
    /**
     * Generate dynamic index by scanning uploads folder
     */
    public function generateDynamicIndex() {
        $index = [
            'hardware' => ['cpus' => [], 'gpus' => []],
            'metadata' => [
                'totalHardware' => 0,
                'totalBenchmarks' => 0,
                'lastUpdated' => time(),
                'version' => '1.0',
                'benchmarkTypes' => ['7zip', 'reversan', 'llama', 'blender']
            ]
        ];
        
        $uploadsDir = $this->dataDir . '/uploads';
        if (!is_dir($uploadsDir)) {
            return $index;
        }
        
        // Scan all upload directories
        $uploadDirs = glob($uploadsDir . '/*', GLOB_ONLYDIR);
        
        foreach ($uploadDirs as $uploadDir) {
            $runId = basename($uploadDir);
            $hardwareFile = $uploadDir . '/hardware_info.json';
            
            if (!file_exists($hardwareFile)) {
                continue;
            }
            
            $hardwareInfo = json_decode(file_get_contents($hardwareFile), true);
            if (!$hardwareInfo) {
                continue;
            }
            
            // Extract hardware identifiers
            $cpuId = $this->generateHardwareId('cpu', $hardwareInfo['cpu']);
            $gpuId = $this->generateHardwareId('gpu', $hardwareInfo['gpu'] ?? '');
            
            // Get benchmark files in this upload
            $benchmarkFiles = [];
            foreach (['7zip', 'reversan', 'llama', 'blender'] as $type) {
                $benchmarkFile = $uploadDir . '/' . $type . '.json';
                if (file_exists($benchmarkFile)) {
                    $benchmarkFiles[$type] = 'uploads/' . $runId . '/' . $type . '.json';
                }
            }
            
            // Update or create CPU entry
            $cpuIndex = $this->findOrCreateHardwareEntry($index['hardware']['cpus'], $cpuId, [
                'id' => $cpuId,
                'name' => $hardwareInfo['cpu'],
                'manufacturer' => $this->extractManufacturer($hardwareInfo['cpu']),
                'cores' => $hardwareInfo['cores'] ?? 0,
                'benchmarks' => [],
                'lastUpdated' => filemtime($uploadDir)
            ]);
            
            // Add benchmark files to CPU entry
            foreach ($benchmarkFiles as $type => $path) {
                if (!isset($index['hardware']['cpus'][$cpuIndex]['benchmarks'][$type])) {
                    $index['hardware']['cpus'][$cpuIndex]['benchmarks'][$type] = [];
                }
                $index['hardware']['cpus'][$cpuIndex]['benchmarks'][$type][] = $path;
            }
            $index['hardware']['cpus'][$cpuIndex]['lastUpdated'] = max($index['hardware']['cpus'][$cpuIndex]['lastUpdated'], filemtime($uploadDir));
            
            // Update or create GPU entry if we have GPU info
            if (!empty($hardwareInfo['gpu']) && $hardwareInfo['gpu'] !== 'Unknown') {
                $gpuIndex = $this->findOrCreateHardwareEntry($index['hardware']['gpus'], $gpuId, [
                    'id' => $gpuId,
                    'name' => $hardwareInfo['gpu'],
                    'manufacturer' => $this->extractManufacturer($hardwareInfo['gpu']),
                    'framework' => $this->detectGpuFramework($hardwareInfo['gpu']),
                    'benchmarks' => [],
                    'lastUpdated' => filemtime($uploadDir)
                ]);
                
                // Add benchmark files to GPU entry (only GPU-capable benchmarks)
                $gpuBenchmarks = array_intersect_key($benchmarkFiles, array_flip(['llama', 'blender']));
                foreach ($gpuBenchmarks as $type => $path) {
                    if (!isset($index['hardware']['gpus'][$gpuIndex]['benchmarks'][$type])) {
                        $index['hardware']['gpus'][$gpuIndex]['benchmarks'][$type] = [];
                    }
                    $index['hardware']['gpus'][$gpuIndex]['benchmarks'][$type][] = $path;
                }
                $index['hardware']['gpus'][$gpuIndex]['lastUpdated'] = max($index['hardware']['gpus'][$gpuIndex]['lastUpdated'], filemtime($uploadDir));
            }
        }
        
        // Update metadata
        $index['metadata']['totalHardware'] = count($index['hardware']['cpus']) + count($index['hardware']['gpus']);
        $index['metadata']['totalBenchmarks'] = $this->countTotalBenchmarks($index['hardware']);
        
        return $index;
    }
    
    /**
     * Find existing hardware entry or create new one
     * Returns the index of the entry in the array
     */
    private function findOrCreateHardwareEntry(&$hardwareList, $id, $template) {
        // Find existing entry
        foreach ($hardwareList as $index => $entry) {
            if ($entry['id'] === $id) {
                return $index;
            }
        }
        
        // Create new entry
        $hardwareList[] = $template;
        return count($hardwareList) - 1;
    }
    
    /**
     * Generate hardware ID from name
     */
    private function generateHardwareId($type, $name) {
        if (empty($name) || $name === 'Unknown') {
            return 'unknown-' . $type;
        }
        
        $id = strtolower($name);
        $id = preg_replace('/[^a-z0-9\s]/', '', $id);
        $id = preg_replace('/\s+/', '-', $id);
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
     * Detect GPU framework from name
     */
    private function detectGpuFramework($gpuName) {
        $name = strtolower($gpuName);
        if (strpos($name, 'amd') !== false || strpos($name, 'radeon') !== false) return 'HIP';
        if (strpos($name, 'nvidia') !== false || strpos($name, 'geforce') !== false || strpos($name, 'rtx') !== false) return 'CUDA';
        return 'OPENCL';
    }
    
    /**
     * Count total benchmarks across all hardware
     */
    private function countTotalBenchmarks($hardware) {
        $total = 0;
        foreach (['cpus', 'gpus'] as $type) {
            foreach ($hardware[$type] as $hw) {
                foreach ($hw['benchmarks'] as $benchmarkType => $files) {
                    $total += count($files);
                }
            }
        }
        return $total;
    }
}
?>