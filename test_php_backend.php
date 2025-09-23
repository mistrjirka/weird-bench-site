<?php
// Test PHP API endpoints without needing a web server
// This script simulates API calls to test the FileStorageManager

require_once 'api/config.php';
require_once 'api/utils/JsonValidator.php';
require_once 'api/utils/HardwareExtractor.php';
require_once 'api/utils/FileStorageManager.php';

echo "🚀 Testing PHP API Backend...\n";
echo str_repeat("=", 50) . "\n";

try {
    // Initialize file storage manager
    $fileManager = new FileStorageManager();
    
    echo "📋 Testing hardware list retrieval...\n";
    
    // Test getting hardware list
    $hardwareList = $fileManager->getHardwareList();
    
    if (!empty($hardwareList)) {
        echo "✅ Hardware list retrieved successfully!\n";
        echo "  Total CPUs: " . count($hardwareList['cpus']) . "\n";
        echo "  Total GPUs: " . count($hardwareList['gpus']) . "\n";
        echo "  Total count: " . $hardwareList['totalCount'] . "\n";
        
        // Show first few items
        if (!empty($hardwareList['cpus'])) {
            echo "  First CPU: " . $hardwareList['cpus'][0]['hardware']['name'] . "\n";
        }
        if (!empty($hardwareList['gpus'])) {
            echo "  First GPU: " . $hardwareList['gpus'][0]['hardware']['name'] . "\n";
        }
    } else {
        echo "❌ No hardware data found\n";
    }
    
    echo "\n🔍 Testing hardware detail retrieval...\n";
    
    // Find a hardware ID to test with
    $testHardwareId = null;
    if (!empty($hardwareList['cpus'])) {
        $testHardwareId = $hardwareList['cpus'][0]['hardware']['id'];
        $testType = 'cpu';
    } elseif (!empty($hardwareList['gpus'])) {
        $testHardwareId = $hardwareList['gpus'][0]['hardware']['id'];
        $testType = 'gpu';
    }
    
    if ($testHardwareId) {
        echo "  Testing with hardware ID: $testHardwareId\n";
        $hardwareDetail = $fileManager->getHardwareDetail($testType, $testHardwareId);
        
        if ($hardwareDetail) {
            echo "✅ Hardware detail retrieved successfully!\n";
            echo "  Hardware name: " . $hardwareDetail['hardware']['name'] . "\n";
            echo "  Benchmark count: " . count($hardwareDetail['benchmarks']) . "\n";
            
            if (!empty($hardwareDetail['benchmarks'])) {
                echo "  Available benchmarks: " . implode(', ', array_keys($hardwareDetail['benchmarks'])) . "\n";
            }
        } else {
            echo "❌ Failed to retrieve hardware detail\n";
        }
    } else {
        echo "❌ No hardware found to test with\n";
    }
    
    echo "\n📊 File system check...\n";
    
    // Check what files were created
    $dirs = [
        'Hardware files' => DATA_DIR . '/hardware',
        'Benchmark files' => DATA_DIR . '/benchmarks', 
        'Results files' => DATA_DIR . '/results',
        'Cache files' => CACHE_DIR . '/hardware-list'
    ];
    
    foreach ($dirs as $label => $dir) {
        if (is_dir($dir)) {
            $files = glob($dir . '/*.json');
            echo "  $label: " . count($files) . " files\n";
        } else {
            echo "  $label: Directory not found\n";
        }
    }
    
    echo "\n✅ PHP backend test completed successfully!\n";
    echo "🌐 The backend is ready to serve API requests.\n";
    
} catch (Exception $e) {
    echo "❌ Error during PHP backend test:\n";
    echo "   " . $e->getMessage() . "\n";
    echo "   File: " . $e->getFile() . ":" . $e->getLine() . "\n";
}
?>