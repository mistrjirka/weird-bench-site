<?php
// Simple test script to simulate benchmark upload

require_once 'api/config.php';
require_once 'api/utils/JsonValidator.php';
require_once 'api/utils/HardwareExtractor.php';
require_once 'api/utils/FileStorageManager.php';

// Sample benchmark data (based on your attachments)
$sampleData = [
    'llama' => [
        'meta' => [
            'benchmark_name' => 'llama',
            'host' => 'test-system',
            'platform' => 'Linux-6.16.7-arch1-1-x86_64-with-glibc2.42',
            'timestamp' => time()
        ],
        'build' => [
            'cpu_build_timing' => [
                'config_time_seconds' => 1.02,
                'build_time_seconds' => 86.45,
                'total_time_seconds' => 87.47
            ]
        ],
        'runs_cpu' => [
            [
                'type' => 'cpu',
                'metrics' => [
                    'decode_tokens_per_second' => 16.6,
                    'prompt_tokens_per_second' => 58.2,
                    'total_time_ms' => 8799.3
                ]
            ]
        ]
    ],
    '7zip' => [
        'meta' => [
            'benchmark_name' => '7zip',
            'host' => 'test-system',
            'platform' => 'Linux-6.16.7-arch1-1-x86_64-with-glibc2.42',
            'timestamp' => time()
        ],
        'build' => [
            'sevenzip_command' => '7z',
            'build_time_seconds' => 0.0
        ],
        'runs' => [
            [
                'success' => true,
                'threads' => 1,
                'elapsed_seconds' => 21.5,
                'archive_size_bytes' => 105010562,
                'compression_ratio' => 0.0,
                'compression_speed_mb_s' => 0.0,
                'raw_output' => 'Test output',
                'speedup' => 1.0
            ],
            [
                'success' => true,
                'threads' => 8,
                'elapsed_seconds' => 5.6,
                'archive_size_bytes' => 105010562,
                'compression_ratio' => 0.0,
                'compression_speed_mb_s' => 0.0,
                'raw_output' => 'Test output',
                'speedup' => 3.84
            ]
        ]
    ]
];

try {
    echo "Testing file storage system...\n";
    
    // Extract hardware info
    $extractor = new HardwareExtractor();
    $hardwareInfo = $extractor->extractFromBenchmarks($sampleData);
    
    echo "Hardware info extracted:\n";
    print_r($hardwareInfo);
    
    // Store benchmarks
    $storage = new FileStorageManager();
    $result = $storage->storeBenchmarks($hardwareInfo, $sampleData);
    
    echo "Storage result:\n";
    print_r($result);
    
    // Test hardware list
    echo "\nHardware list:\n";
    $list = $storage->getHardwareList();
    print_r($list);
    
    echo "\nTest completed successfully!\n";
    
} catch (Exception $e) {
    echo "Error: " . $e->getMessage() . "\n";
    echo "Trace:\n" . $e->getTraceAsString() . "\n";
}
