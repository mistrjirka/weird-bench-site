&lt;?php
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
require_once 'utils/FileStorageManager.php';

try {
    // Route the request
    $requestUri = parse_url($_SERVER['REQUEST_URI'], PHP_URL_PATH);
    $method = $_SERVER['REQUEST_METHOD'];
    
    // Remove /api prefix if present
    $requestUri = preg_replace('/^\/api/', '', $requestUri);
    
    switch (true) {
        case $method === 'POST' && $requestUri === '/upload':
            handleUpload();
            break;
            
        case $method === 'GET' && $requestUri === '/hardware':
            handleHardwareList();
            break;
            
        case $method === 'GET' && preg_match('/^\/hardware\/(cpu|gpu)\/(.+)$/', $requestUri, $matches):
            handleHardwareDetail($matches[1], $matches[2]);
            break;
            
        case $method === 'GET' && $requestUri === '/health':
            handleHealthCheck();
            break;
            
        default:
            http_response_code(404);
            echo json_encode([
                'success' => false,
                'error' => 'Endpoint not found',
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
            // Handle file uploads
            $files = ['llama', '7zip', 'reversan', 'blender'];
            $benchmarkData = [];
            
            foreach ($files as $fileType) {
                if (!isset($_FILES[$fileType])) {
                    throw new Exception("Missing required file: $fileType");
                }
                
                $file = $_FILES[$fileType];
                if ($file['error'] !== UPLOAD_ERR_OK) {
                    throw new Exception("Upload error for $fileType: " . $file['error']);
                }
                
                $content = file_get_contents($file['tmp_name']);
                $json = json_decode($content, true);
                
                if (json_last_error() !== JSON_ERROR_NONE) {
                    throw new Exception("Invalid JSON in $fileType: " . json_last_error_msg());
                }
                
                $benchmarkData[$fileType] = $json;
            }
        } else {
            // Handle JSON payload
            $input = json_decode(file_get_contents('php://input'), true);
            if (json_last_error() !== JSON_ERROR_NONE) {
                throw new Exception('Invalid JSON payload: ' . json_last_error_msg());
            }
            
            $benchmarkData = $input;
        }
        
        // Validate all benchmark data
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
        
        // Extract hardware information
        $extractor = new HardwareExtractor();
        $hardwareInfo = $extractor->extractFromBenchmarks($benchmarkData);
        
        // Store in file system
        $storage = new FileStorageManager();
        $result = $storage->storeBenchmarks($hardwareInfo, $benchmarkData);
        
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
 * Get list of all hardware with benchmark summaries
 */
function handleHardwareList() {
    try {
        $storage = new FileStorageManager();
        $hardwareList = $storage->getHardwareList();
        
        echo json_encode([
            'success' => true,
            'data' => $hardwareList,
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
 * Get detailed hardware information with all benchmarks
 */
function handleHardwareDetail($type, $id) {
    try {
        $storage = new FileStorageManager();
        $hardware = $storage->getHardwareDetail($type, $id);
        
        if (!$hardware) {
            http_response_code(404);
            echo json_encode([
                'success' => false,
                'error' => 'Hardware not found',
                'timestamp' => time()
            ]);
            return;
        }
        
        echo json_encode([
            'success' => true,
            'data' => $hardware,
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
 * Health check endpoint
 */
function handleHealthCheck() {
    echo json_encode([
        'success' => true,
        'status' => 'healthy',
        'version' => '1.0.0',
        'timestamp' => time()
    ]);
}
?&gt;