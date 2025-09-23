<?php
// Simple API endpoint tester - simulates HTTP requests to our API
header('Content-Type: application/json');

// Simple router to test different endpoints
$endpoint = $_GET['endpoint'] ?? 'hardware-list';

switch($endpoint) {
    case 'hardware-list':
        testHardwareListEndpoint();
        break;
    case 'health':
        testHealthEndpoint();
        break;
    default:
        http_response_code(404);
        echo json_encode(['error' => 'Endpoint not found']);
}

function testHardwareListEndpoint() {
    try {
        // Load the cached hardware list directly
        $cacheFile = __DIR__ . '/api/cache/hardware-list/list.json';
        
        if (!file_exists($cacheFile)) {
            http_response_code(404);
            echo json_encode([
                'success' => false,
                'error' => 'Hardware list cache not found',
                'message' => 'Run the test_file_storage.py script first'
            ]);
            return;
        }
        
        $data = json_decode(file_get_contents($cacheFile), true);
        
        if ($data === null) {
            http_response_code(500);
            echo json_encode([
                'success' => false,
                'error' => 'Failed to decode hardware list cache'
            ]);
            return;
        }
        
        // Format response like the real API
        $response = [
            'success' => true,
            'data' => $data,
            'message' => 'Hardware list retrieved successfully',
            'timestamp' => time()
        ];
        
        echo json_encode($response, JSON_PRETTY_PRINT);
        
    } catch (Exception $e) {
        http_response_code(500);
        echo json_encode([
            'success' => false,
            'error' => 'Server error: ' . $e->getMessage()
        ]);
    }
}

function testHealthEndpoint() {
    $checks = [
        'cache_dir' => is_dir(__DIR__ . '/api/cache'),
        'data_dir' => is_dir(__DIR__ . '/api/data'),
        'hardware_cache' => file_exists(__DIR__ . '/api/cache/hardware-list/list.json'),
        'hardware_data' => !empty(glob(__DIR__ . '/api/data/hardware/*.json')),
        'benchmark_data' => !empty(glob(__DIR__ . '/api/data/benchmarks/*.json'))
    ];
    
    $allHealthy = array_reduce($checks, function($carry, $check) {
        return $carry && $check;
    }, true);
    
    http_response_code($allHealthy ? 200 : 503);
    
    echo json_encode([
        'success' => $allHealthy,
        'status' => $allHealthy ? 'healthy' : 'unhealthy',
        'checks' => $checks,
        'message' => $allHealthy ? 'All systems operational' : 'Some systems are not ready',
        'timestamp' => time()
    ], JSON_PRETTY_PRINT);
}
?>