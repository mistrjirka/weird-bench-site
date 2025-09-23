&lt;?php
class HardwareExtractor {
    
    /**
     * Extract hardware information from all benchmark data
     */
    public function extractFromBenchmarks($benchmarkData) {
        $hardwareInfo = [
            'cpus' => [],
            'gpus' => [],
            'memory' => null,
            'os' => null,
            'timestamp' => time()
        ];

        // Extract from each benchmark type
        foreach ($benchmarkData as $type => $data) {
            switch ($type) {
                case 'llama':
                    $this->extractFromLlama($data, $hardwareInfo);
                    break;
                case '7zip':
                    $this->extractFrom7zip($data, $hardwareInfo);
                    break;
                case 'reversan':
                    $this->extractFromReversan($data, $hardwareInfo);
                    break;
                case 'blender':
                    $this->extractFromBlender($data, $hardwareInfo);
                    break;
            }
        }

        // Generate unique hardware ID
        $hardwareInfo['id'] = $this->generateHardwareId($hardwareInfo);

        return $hardwareInfo;
    }

    /**
     * Extract hardware info from Llama benchmark
     */
    private function extractFromLlama($data, &$hardwareInfo) {
        if (isset($data['system_info'])) {
            $sysInfo = $data['system_info'];
            
            // CPU info
            if (isset($sysInfo['cpu'])) {
                $cpu = $this->normalizeCpuInfo($sysInfo['cpu']);
                if (!$this->hardwareExists($hardwareInfo['cpus'], $cpu)) {
                    $hardwareInfo['cpus'][] = $cpu;
                }
            }
            
            // GPU info from CUDA/ROCm
            if (isset($sysInfo['cuda_devices'])) {
                foreach ($sysInfo['cuda_devices'] as $device) {
                    $gpu = [
                        'name' => $device['name'] ?? 'Unknown CUDA Device',
                        'type' => 'gpu',
                        'manufacturer' => $this->detectGpuManufacturer($device['name'] ?? ''),
                        'memory' => isset($device['memory']) ? (int)$device['memory'] : null,
                        'framework' => 'CUDA'
                    ];
                    if (!$this->hardwareExists($hardwareInfo['gpus'], $gpu)) {
                        $hardwareInfo['gpus'][] = $gpu;
                    }
                }
            }
            
            if (isset($sysInfo['rocm_devices'])) {
                foreach ($sysInfo['rocm_devices'] as $device) {
                    $gpu = [
                        'name' => $device['name'] ?? 'Unknown ROCm Device',
                        'type' => 'gpu',
                        'manufacturer' => 'AMD',
                        'memory' => isset($device['memory']) ? (int)$device['memory'] : null,
                        'framework' => 'HIP'
                    ];
                    if (!$this->hardwareExists($hardwareInfo['gpus'], $gpu)) {
                        $hardwareInfo['gpus'][] = $gpu;
                    }
                }
            }
            
            // System info
            if (isset($sysInfo['memory']) && !$hardwareInfo['memory']) {
                $hardwareInfo['memory'] = $sysInfo['memory'];
            }
            if (isset($sysInfo['os']) && !$hardwareInfo['os']) {
                $hardwareInfo['os'] = $sysInfo['os'];
            }
        }
    }

    /**
     * Extract hardware info from 7zip benchmark
     */
    private function extractFrom7zip($data, &$hardwareInfo) {
        if (isset($data['system_info']['cpu'])) {
            $cpu = $this->normalizeCpuInfo($data['system_info']['cpu']);
            if (!$this->hardwareExists($hardwareInfo['cpus'], $cpu)) {
                $hardwareInfo['cpus'][] = $cpu;
            }
        }
        
        if (isset($data['system_info']['memory']) && !$hardwareInfo['memory']) {
            $hardwareInfo['memory'] = $data['system_info']['memory'];
        }
        if (isset($data['system_info']['os']) && !$hardwareInfo['os']) {
            $hardwareInfo['os'] = $data['system_info']['os'];
        }
    }

    /**
     * Extract hardware info from Reversan benchmark  
     */
    private function extractFromReversan($data, &$hardwareInfo) {
        if (isset($data['system_info']['cpu'])) {
            $cpu = $this->normalizeCpuInfo($data['system_info']['cpu']);
            if (!$this->hardwareExists($hardwareInfo['cpus'], $cpu)) {
                $hardwareInfo['cpus'][] = $cpu;
            }
        }
        
        if (isset($data['system_info']['memory']) && !$hardwareInfo['memory']) {
            $hardwareInfo['memory'] = $data['system_info']['memory'];
        }
        if (isset($data['system_info']['os']) && !$hardwareInfo['os']) {
            $hardwareInfo['os'] = $data['system_info']['os'];
        }
    }

    /**
     * Extract hardware info from Blender benchmark
     */
    private function extractFromBlender($data, &$hardwareInfo) {
        if (isset($data['system_info']['cpu'])) {
            $cpu = $this->normalizeCpuInfo($data['system_info']['cpu']);
            if (!$this->hardwareExists($hardwareInfo['cpus'], $cpu)) {
                $hardwareInfo['cpus'][] = $cpu;
            }
        }
        
        // Extract GPU info from benchmark results
        if (isset($data['benchmark_results'])) {
            foreach ($data['benchmark_results'] as $result) {
                if (isset($result['device_name']) && $result['device_name'] !== 'CPU') {
                    $gpu = [
                        'name' => $result['device_name'],
                        'type' => 'gpu',
                        'manufacturer' => $this->detectGpuManufacturer($result['device_name']),
                        'framework' => $this->mapBlenderFramework($result['device_framework'] ?? 'UNKNOWN')
                    ];
                    if (!$this->hardwareExists($hardwareInfo['gpus'], $gpu)) {
                        $hardwareInfo['gpus'][] = $gpu;
                    }
                }
            }
        }
        
        if (isset($data['system_info']['memory']) && !$hardwareInfo['memory']) {
            $hardwareInfo['memory'] = $data['system_info']['memory'];
        }
        if (isset($data['system_info']['os']) && !$hardwareInfo['os']) {
            $hardwareInfo['os'] = $data['system_info']['os'];
        }
    }

    /**
     * Normalize CPU information
     */
    private function normalizeCpuInfo($cpuData) {
        if (is_string($cpuData)) {
            return [
                'name' => $cpuData,
                'type' => 'cpu',
                'manufacturer' => $this->detectCpuManufacturer($cpuData)
            ];
        }
        
        return [
            'name' => $cpuData['name'] ?? $cpuData['model'] ?? 'Unknown CPU',
            'type' => 'cpu',
            'manufacturer' => $this->detectCpuManufacturer($cpuData['name'] ?? $cpuData['model'] ?? ''),
            'cores' => isset($cpuData['cores']) ? (int)$cpuData['cores'] : null,
            'threads' => isset($cpuData['threads']) ? (int)$cpuData['threads'] : null,
            'frequency' => isset($cpuData['frequency']) ? $cpuData['frequency'] : null
        ];
    }

    /**
     * Detect CPU manufacturer from name
     */
    private function detectCpuManufacturer($name) {
        $name = strtolower($name);
        if (strpos($name, 'intel') !== false) return 'Intel';
        if (strpos($name, 'amd') !== false) return 'AMD';
        if (strpos($name, 'ryzen') !== false) return 'AMD';
        if (strpos($name, 'epyc') !== false) return 'AMD';
        if (strpos($name, 'threadripper') !== false) return 'AMD';
        if (strpos($name, 'xeon') !== false) return 'Intel';
        if (strpos($name, 'core') !== false) return 'Intel';
        if (strpos($name, 'celeron') !== false) return 'Intel';
        if (strpos($name, 'pentium') !== false) return 'Intel';
        return 'Unknown';
    }

    /**
     * Detect GPU manufacturer from name
     */
    private function detectGpuManufacturer($name) {
        $name = strtolower($name);
        if (strpos($name, 'nvidia') !== false || strpos($name, 'geforce') !== false || strpos($name, 'rtx') !== false || strpos($name, 'gtx') !== false) {
            return 'NVIDIA';
        }
        if (strpos($name, 'amd') !== false || strpos($name, 'radeon') !== false || strpos($name, 'rx ') !== false) {
            return 'AMD';
        }
        if (strpos($name, 'intel') !== false || strpos($name, 'arc') !== false) {
            return 'Intel';
        }
        return 'Unknown';
    }

    /**
     * Map Blender device framework to standard framework
     */
    private function mapBlenderFramework($framework) {
        $frameworkMap = [
            'CUDA' => 'CUDA',
            'HIP' => 'HIP', 
            'OPTIX' => 'OPTIX',
            'OPENCL' => 'OPENCL',
            'METAL' => 'METAL',
            'ONEAPI' => 'ONEAPI'
        ];
        
        return $frameworkMap[strtoupper($framework)] ?? 'UNKNOWN';
    }

    /**
     * Check if hardware already exists in list
     */
    private function hardwareExists($hardwareList, $newHardware) {
        foreach ($hardwareList as $existing) {
            if ($this->isSameHardware($existing, $newHardware)) {
                return true;
            }
        }
        return false;
    }

    /**
     * Check if two hardware entries represent the same device
     */
    private function isSameHardware($hw1, $hw2) {
        $name1 = $this->normalizeHardwareName($hw1['name']);
        $name2 = $this->normalizeHardwareName($hw2['name']);
        
        return $name1 === $name2 && $hw1['type'] === $hw2['type'];
    }

    /**
     * Normalize hardware name for comparison
     */
    private function normalizeHardwareName($name) {
        // Remove extra whitespace and common suffixes
        $name = preg_replace('/\s+/', ' ', trim($name));
        $name = preg_replace('/ \(.*?\)$/', '', $name); // Remove parenthetical info
        $name = str_replace([' Processor', ' CPU', ' Graphics'], '', $name);
        
        return strtolower($name);
    }

    /**
     * Generate unique hardware ID based on hardware configuration
     */
    private function generateHardwareId($hardwareInfo) {
        $components = [];
        
        // Add CPU info
        foreach ($hardwareInfo['cpus'] as $cpu) {
            $components[] = 'cpu-' . $this->slugify($cpu['name']);
        }
        
        // Add GPU info  
        foreach ($hardwareInfo['gpus'] as $gpu) {
            $components[] = 'gpu-' . $this->slugify($gpu['name']);
        }
        
        // Add memory if available
        if ($hardwareInfo['memory']) {
            $components[] = 'mem-' . $this->slugify($hardwareInfo['memory']);
        }
        
        return implode('-', $components);
    }

    /**
     * Convert string to URL-friendly slug
     */
    private function slugify($text) {
        $text = strtolower($text);
        $text = preg_replace('/[^a-z0-9\s-]/', '', $text);
        $text = preg_replace('/[\s-]+/', '-', $text);
        return trim($text, '-');
    }
}
?&gt;