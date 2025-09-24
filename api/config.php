<?php
// File storage configuration
define('MAX_FILE_SIZE', 10 * 1024 * 1024); // 10MB
define('UPLOAD_DIR', __DIR__ . '/uploads');
define('DATA_DIR', __DIR__ . '/data');
define('CACHE_DIR', __DIR__ . '/cache');

// Docker-specific paths
if (isset($_SERVER['HTTP_HOST']) && $_SERVER['HTTP_HOST'] === 'localhost:8090') {
    define('PUBLIC_DATA_DIR', '/var/www/html/public/data');
} else {
    define('PUBLIC_DATA_DIR', __DIR__ . '/../public/data');
}

// Schema directory
define('SCHEMA_DIR', __DIR__ . '/../schemas');

// Ensure directories exist
$directories = [UPLOAD_DIR, DATA_DIR, CACHE_DIR];
foreach ($directories as $dir) {
    if (!is_dir($dir)) {
        mkdir($dir, 0755, true);
    }
}
?>