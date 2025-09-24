<?php
header('Content-Type: application/json');
header('Access-Control-Allow-Origin: *');
header('Access-Control-Allow-Methods: GET, POST, OPTIONS');
header('Access-Control-Allow-Headers: Content-Type, Authorization');

// Handle preflight requests
if ($_SERVER['REQUEST_METHOD'] === 'OPTIONS') {
    http_response_code(200);
    exit();
}

// Error reporting
error_reporting(E_ALL);
ini_set('display_errors', 0); // Don't display errors to client

// Load configuration
require_once 'config.php';
require_once 'utils/JsonValidator.php';
require_once 'utils/HardwareExtractor.php';
require_once 'utils/SimpleStorageManager.php';

try {
    $method = $_SERVER['REQUEST_METHOD'];
    $action = $_GET['action'] ?? $_POST['action'] ?? '';
    
    
    switch ($action) {
        case 'upload':
            if ($method !== 'POST') {
                throw new Exception('Upload requires POST method');
            }
            handleUpload();
            break;
            
        case 'hardware':
            if ($method !== 'GET') {
                throw new Exception('Hardware list requires GET method');
            }
            handleHardwareList();
            break;
            
        case 'hardware-detail':
            if ($method !== 'GET') {
                throw new Exception('Hardware detail requires GET method');
            }
            $type = $_GET['type'] ?? '';
            $id = $_GET['id'] ?? '';
            if (!$type || !$id) {
                throw new Exception('Type and ID parameters required');
            }
            handleHardwareDetail($type, $id);
            break;
            
        case 'health':
            handleHealthCheck();
            break;
            
        default:
            http_response_code(400);
            echo json_encode([
                'success' => false,
                'error' => 'Invalid or missing action parameter',
                'available_actions' => ['upload', 'hardware', 'hardware-detail', 'health'],
                'timestamp' => time()
            ]);
    }
    
} catch (Exception $e) {
    http_response_code(500);
    echo json_encode([
        'success' => false,
        'error' => 'Internal server error',
        'message' => $e->getMessage(),
        'timestamp' => time()
    ]);
}

/**
 * Handle benchmark data upload from run_benchmarks.py
 */
function handleUpload() {
    try {
        // Check if this is multipart/form-data or JSON
        $contentType = $_SERVER['CONTENT_TYPE'] ?? '';
        
        if (strpos($contentType, 'multipart/form-data') !== false) {
            // Handle file uploads from new benchmark script
            $benchmarkData = [];
            $runId = $_POST['run_id'] ?? null;
            $hardwareInfo = isset($_POST['hardware_info']) ? json_decode($_POST['hardware_info'], true) : null;
            
            // Handle dynamic file uploads (new format with _results suffix)
            foreach ($_FILES as $fileKey => $file) {
                if ($file['error'] !== UPLOAD_ERR_OK) {
                    continue; // Skip files with errors
                }
                
                $content = file_get_contents($file['tmp_name']);
                $json = json_decode($content, true);
                
                if (json_last_error() !== JSON_ERROR_NONE) {
                    throw new Exception("Invalid JSON in $fileKey: " . json_last_error_msg());
                }
                
                // Extract benchmark type from file key (remove _results suffix)
                $benchmarkType = str_replace('_results', '', $fileKey);
                
                // Extract the actual benchmark data from the results structure
                if (isset($json['results'])) {
                    $benchmarkData[$benchmarkType] = $json['results'];
                } else {
                    $benchmarkData[$benchmarkType] = $json;
                }
            }
            
            // If no files were processed but we have old format files, try those
            if (empty($benchmarkData)) {
                $files = ['llama', '7zip', 'reversan', 'blender'];
                foreach ($files as $fileType) {
                    if (isset($_FILES[$fileType]) && $_FILES[$fileType]['error'] === UPLOAD_ERR_OK) {
                        $file = $_FILES[$fileType];
                        $content = file_get_contents($file['tmp_name']);
                        $json = json_decode($content, true);
                        
                        if (json_last_error() !== JSON_ERROR_NONE) {
                            throw new Exception("Invalid JSON in $fileType: " . json_last_error_msg());
                        }
                        
                        $benchmarkData[$fileType] = $json;
                    }
                }
            }
        } else {
            // Handle JSON payload
            $input = json_decode(file_get_contents('php://input'), true);
            if (json_last_error() !== JSON_ERROR_NONE) {
                throw new Exception('Invalid JSON payload: ' . json_last_error_msg());
            }
            
            $benchmarkData = $input;
        }
        
        // Skip validation for now to test storage
        // TODO: Re-enable validation once data structure is confirmed
        /*
        $validator = new JsonValidator();
        $errors = [];
        
        foreach ($benchmarkData as $type => $data) {
            $validation = $validator->validate($type, $data);
            if (!$validation['valid']) {
                $errors[$type] = $validation['errors'];
            }
        }
        
        if (!empty($errors)) {
            http_response_code(400);
            echo json_encode([
                'success' => false,
                'error' => 'Validation failed',
                'validation_errors' => $errors,
                'timestamp' => time()
            ]);
            return;
        }
        */
        
        // Extract hardware information (use provided info if available)
        if (!$hardwareInfo) {
            $extractor = new HardwareExtractor();
            $hardwareInfo = $extractor->extractFromBenchmarks($benchmarkData);
        }
        
        // Store in file system using simple storage manager
        $storage = new SimpleStorageManager();
        $result = $storage->storeBenchmarks($hardwareInfo, $benchmarkData, $runId);
        
        // Return success response
        echo json_encode([
            'success' => true,
            'data' => array_merge($result, ['hardware_info' => $hardwareInfo]),
            'message' => 'Benchmarks uploaded successfully',
            'timestamp' => time()
        ]);
        
    } catch (Exception $e) {
        http_response_code(400);
        echo json_encode([
            'success' => false,
            'error' => $e->getMessage(),
            'timestamp' => time()
        ]);
    }
}

/**
 * Get list of all hardware with benchmark summaries - dynamically generated
 */
function handleHardwareList() {
    try {
        $storage = new SimpleStorageManager();
        $indexData = $storage->generateDynamicIndex();
        
        echo json_encode([
            'success' => true,
            'data' => $indexData,
            'timestamp' => time()
        ]);
        
    } catch (Exception $e) {
        http_response_code(500);
        echo json_encode([
            'success' => false,
            'error' => $e->getMessage(),
            'timestamp' => time()
        ]);
    }
}

/**
 * Get detailed hardware information with all benchmarks - dynamically generated
 */
function handleHardwareDetail($type, $id) {
    try {
        $storage = new SimpleStorageManager();
        $indexData = $storage->generateDynamicIndex();
        
        // Find the hardware in the dynamic index
        $hardware = null;
        $hardwareList = $type === 'cpu' ? $indexData['hardware']['cpus'] : $indexData['hardware']['gpus'];
        
        foreach ($hardwareList as $hw) {
            if ($hw['id'] === $id) {
                $hardware = $hw;
                break;
            }
        }
        
        if (!$hardware) {
            http_response_code(404);
            echo json_encode([
                'success' => false,
                'error' => 'Hardware not found',
                'timestamp' => time()
            ]);
            return;
        }

        // Load actual benchmark file contents
        $hardwareWithData = $hardware;
        $benchmarkData = [];
        
        foreach ($hardware['benchmarks'] as $benchmarkType => $filePaths) {
            foreach ($filePaths as $filePath) {
                $fullPath = dirname(__DIR__) . '/public/data/' . $filePath;
                if (file_exists($fullPath)) {
                    $content = file_get_contents($fullPath);
                    $json = json_decode($content, true);
                    if ($json) {
                        $benchmarkData[] = [
                            'type' => $benchmarkType,
                            'data' => $json,
                            'filePath' => $filePath
                        ];
                    }
                }
            }
        }
        
        $hardwareWithData['benchmarkFiles'] = $benchmarkData;

        echo json_encode([
            'success' => true,
            'data' => $hardwareWithData,
            'timestamp' => time()
        ]);    } catch (Exception $e) {
        http_response_code(500);
        echo json_encode([
            'success' => false,
            'error' => $e->getMessage(),
            'timestamp' => time()
        ]);
    }
}

/**
 * Health check endpoint
 */
function handleHealthCheck() {
    echo json_encode([
        'success' => true,
        'status' => 'healthy',
        'version' => '1.0.0',
        'timestamp' => time(),
        'php_version' => phpversion()
    ]);
}


?>