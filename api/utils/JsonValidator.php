&lt;?php
class JsonValidator {
    private $schemas = [];

    public function __construct() {
        $this->loadSchemas();
    }

    /**
     * Load JSON schemas from files
     */
    private function loadSchemas() {
        $schemaFiles = [
            'llama' => SCHEMA_DIR . '/llama_schema.json',
            '7zip' => SCHEMA_DIR . '/7zip_schema.json',
            'reversan' => SCHEMA_DIR . '/reversan_schema.json',
            'blender' => SCHEMA_DIR . '/blender_schema.json'
        ];

        foreach ($schemaFiles as $type => $file) {
            if (file_exists($file)) {
                $content = file_get_contents($file);
                $this->schemas[$type] = json_decode($content, true);
            } else {
                throw new Exception("Schema file not found: $file");
            }
        }
    }

    /**
     * Validate benchmark data against schema
     */
    public function validate($type, $data) {
        if (!isset($this->schemas[$type])) {
            return [
                'valid' => false,
                'errors' => ["Unknown benchmark type: $type"]
            ];
        }

        $schema = $this->schemas[$type];
        $errors = [];

        // Validate based on type
        switch ($type) {
            case 'llama':
                $errors = $this->validateLlama($data, $schema);
                break;
            case '7zip':
                $errors = $this->validate7zip($data, $schema);
                break;
            case 'reversan':
                $errors = $this->validateReversan($data, $schema);
                break;
            case 'blender':
                $errors = $this->validateBlender($data, $schema);
                break;
        }

        return [
            'valid' => empty($errors),
            'errors' => $errors
        ];
    }

    /**
     * Validate Llama benchmark data
     */
    private function validateLlama($data, $schema) {
        $errors = [];

        // Check required fields
        $required = ['system_info', 'benchmark_results', 'test_parameters'];
        foreach ($required as $field) {
            if (!isset($data[$field])) {
                $errors[] = "Missing required field: $field";
            }
        }

        // Validate system_info
        if (isset($data['system_info'])) {
            $sysInfo = $data['system_info'];
            $requiredSysFields = ['cpu', 'memory', 'os'];
            foreach ($requiredSysFields as $field) {
                if (!isset($sysInfo[$field]) || empty($sysInfo[$field])) {
                    $errors[] = "Missing or empty system_info.$field";
                }
            }
        }

        // Validate benchmark_results
        if (isset($data['benchmark_results'])) {
            if (!is_array($data['benchmark_results'])) {
                $errors[] = "benchmark_results must be an array";
            } else {
                foreach ($data['benchmark_results'] as $i => $result) {
                    if (!isset($result['model']) || !isset($result['backend']) || !isset($result['threads'])) {
                        $errors[] = "benchmark_results[$i]: missing required fields (model, backend, threads)";
                    }
                    if (!isset($result['performance']) || !is_numeric($result['performance'])) {
                        $errors[] = "benchmark_results[$i]: performance must be a number";
                    }
                }
            }
        }

        return $errors;
    }

    /**
     * Validate 7zip benchmark data
     */
    private function validate7zip($data, $schema) {
        $errors = [];

        $required = ['system_info', 'benchmark_results'];
        foreach ($required as $field) {
            if (!isset($data[$field])) {
                $errors[] = "Missing required field: $field";
            }
        }

        if (isset($data['benchmark_results'])) {
            if (!is_array($data['benchmark_results'])) {
                $errors[] = "benchmark_results must be an array";
            } else {
                foreach ($data['benchmark_results'] as $i => $result) {
                    if (!isset($result['threads']) || !is_numeric($result['threads'])) {
                        $errors[] = "benchmark_results[$i]: threads must be a number";
                    }
                    if (!isset($result['compression_rating']) || !is_numeric($result['compression_rating'])) {
                        $errors[] = "benchmark_results[$i]: compression_rating must be a number";
                    }
                    if (!isset($result['decompression_rating']) || !is_numeric($result['decompression_rating'])) {
                        $errors[] = "benchmark_results[$i]: decompression_rating must be a number";
                    }
                }
            }
        }

        return $errors;
    }

    /**
     * Validate Reversan benchmark data
     */
    private function validateReversan($data, $schema) {
        $errors = [];

        $required = ['system_info', 'benchmark_results', 'test_parameters'];
        foreach ($required as $field) {
            if (!isset($data[$field])) {
                $errors[] = "Missing required field: $field";
            }
        }

        if (isset($data['benchmark_results'])) {
            if (!is_array($data['benchmark_results'])) {
                $errors[] = "benchmark_results must be an array";
            } else {
                foreach ($data['benchmark_results'] as $i => $result) {
                    if (!isset($result['threads']) || !is_numeric($result['threads'])) {
                        $errors[] = "benchmark_results[$i]: threads must be a number";
                    }
                    if (!isset($result['elapsed_time']) || !is_numeric($result['elapsed_time'])) {
                        $errors[] = "benchmark_results[$i]: elapsed_time must be a number";
                    }
                }
            }
        }

        return $errors;
    }

    /**
     * Validate Blender benchmark data
     */
    private function validateBlender($data, $schema) {
        $errors = [];

        $required = ['system_info', 'benchmark_results'];
        foreach ($required as $field) {
            if (!isset($data[$field])) {
                $errors[] = "Missing required field: $field";
            }
        }

        if (isset($data['benchmark_results'])) {
            if (!is_array($data['benchmark_results'])) {
                $errors[] = "benchmark_results must be an array";
            } else {
                foreach ($data['benchmark_results'] as $i => $result) {
                    if (!isset($result['device_name']) || empty($result['device_name'])) {
                        $errors[] = "benchmark_results[$i]: device_name is required";
                    }
                    if (!isset($result['device_framework'])) {
                        $errors[] = "benchmark_results[$i]: device_framework is required";
                    }
                    if (!isset($result['render_time']) || !is_numeric($result['render_time'])) {
                        $errors[] = "benchmark_results[$i]: render_time must be a number";
                    }
                    if (!isset($result['samples_per_minute']) || !is_numeric($result['samples_per_minute'])) {
                        $errors[] = "benchmark_results[$i]: samples_per_minute must be a number";
                    }
                }
            }
        }

        return $errors;
    }
}
?&gt;