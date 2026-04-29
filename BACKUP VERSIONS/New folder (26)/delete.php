<?php
/**
 * Database Cleanup Utility for Crypto Bot
 * Allows emptying all tables in the crypto_data database with one click
 */

// Database configuration - UPDATE THESE WITH YOUR CREDENTIALS
$db_host = 'localhost';
$db_user = 'root';      // Change to your MySQL username
$db_pass = 'toor';          // Change to your MySQL password
$db_name = 'crypto_data';

// Create connection
$conn = new mysqli($db_host, $db_user, $db_pass, $db_name);

// Check connection
if ($conn->connect_error) {
    die("Connection failed: " . $conn->connect_error);
}

// Set charset
$conn->set_charset("utf8mb4");

// Handle cleanup actions
$message = '';
$message_type = '';

// Helper functions
function getTableType($table) {
    if (strpos($table, 'patterns_') === 0) return 'pattern';
    if (strpos($table, 'weights_') === 0) return 'weight';
    if (strpos($table, 'ohlcv') !== false) return 'data';
    if (strpos($table, 'trade') !== false || strpos($table, 'gainers') !== false || strpos($table, 'losers') !== false) return 'trading';
    return 'other';
}

function getTableDescription($table) {
    $descriptions = [
        'patterns_1m' => '1-minute candlestick patterns for short-term trading',
        'patterns_5m' => '5-minute candlestick patterns',
        'patterns_15m' => '15-minute candlestick patterns',
        'patterns_1h' => '1-hour candlestick patterns for swing trading',
        'patterns_4h' => '4-hour candlestick patterns',
        'patterns_1d' => 'Daily candlestick patterns for position trading',
        'ohlcv_data' => 'Raw OHLCV candle data from exchanges',
        'ohlcv_data_superbot' => 'Historical OHLCV data for SuperBot',
        'ohlcv' => 'Legacy OHLCV data',
        'daily_gainers' => 'Daily top gainers list',
        'daily_gainers_losers' => 'Daily gainers and losers data',
        'binance_all_pairs' => 'All Binance trading pairs (spot & futures)',
        'binance_categories' => 'Binance coin categories and sectors',
        'coin_categories' => 'Categorized coin sectors for rotation analysis',
        'coin_sectors' => 'Coin sector classification data',
        'exchange_symbols' => 'Available trading symbols across exchanges',
        'predictions_log' => 'Historical bot predictions and accuracy',
        'realtime_trades' => 'Real-time trade data from WebSocket feeds',
        'trades' => 'Executed trade history',
        'backtest_results' => 'Strategy backtesting results',
        'confidence_thresholds' => 'Model confidence thresholds per timeframe'
    ];
    
    foreach ($descriptions as $key => $desc) {
        if (strpos($table, $key) !== false || $table === $key) {
            return $desc;
        }
    }
    
    if (strpos($table, 'weights_') === 0) {
        $parts = explode('_', $table);
        if (count($parts) >= 3) {
            return ucfirst($parts[1]) . ' weights for ' . $parts[2] . ' timeframe patterns';
        }
        return 'Pattern weight coefficients for prediction';
    }
    
    return 'System table - handle with care';
}

function logCleanupAction($conn, $truncated, $failed) {
    $log_file = __DIR__ . '/cleanup_log.txt';
    $timestamp = date('Y-m-d H:i:s');
    $ip = $_SERVER['REMOTE_ADDR'] ?? 'unknown';
    
    $log_entry = "[$timestamp] IP: $ip\n";
    $log_entry .= "Truncated tables: " . implode(', ', $truncated) . "\n";
    $log_entry .= "Failed tables: " . implode(', ', $failed) . "\n";
    $log_entry .= "----------------------------------------\n";
    
    file_put_contents($log_file, $log_entry, FILE_APPEND);
    
    // Also log to a database table if it exists
    $conn->query("CREATE TABLE IF NOT EXISTS cleanup_log (
        id INT AUTO_INCREMENT PRIMARY KEY,
        action_time DATETIME DEFAULT CURRENT_TIMESTAMP,
        ip_address VARCHAR(45),
        truncated_tables TEXT,
        failed_tables TEXT,
        user_agent TEXT
    )");
    
    $stmt = $conn->prepare("INSERT INTO cleanup_log (ip_address, truncated_tables, failed_tables, user_agent) VALUES (?, ?, ?, ?)");
    $user_agent = $_SERVER['HTTP_USER_AGENT'] ?? '';
    $truncated_str = implode(', ', $truncated);
    $failed_str = implode(', ', $failed);
    $stmt->bind_param("ssss", $ip, $truncated_str, $failed_str, $user_agent);
    $stmt->execute();
    $stmt->close();
}

// Process form submission
if ($_SERVER['REQUEST_METHOD'] === 'POST') {
    if (isset($_POST['confirm']) && $_POST['confirm'] === 'yes') {
        
        // Define all tables
        $all_tables = [
            'weights_close_15m', 'weights_close_1d', 'weights_close_1h', 'weights_close_1m', 
            'weights_close_4h', 'weights_close_5m', 'weights_high_15m', 'weights_high_1d', 
            'weights_high_1h', 'weights_high_1m', 'weights_high_4h', 'weights_high_5m', 
            'weights_low_15m', 'weights_low_1d', 'weights_low_1h', 'weights_low_1m', 
            'weights_low_4h', 'weights_low_5m', 'patterns_15m', 'patterns_1d', 'patterns_1h', 
            'patterns_1m', 'patterns_4h', 'patterns_5m', 'ohlcv_data', 'ohlcv_data_superbot', 
            'ohlcv', 'daily_gainers', 'daily_gainers_losers', 'binance_all_pairs', 
            'binance_categories', 'coin_categories', 'coin_sectors', 'exchange_symbols', 
            'predictions_log', 'realtime_trades', 'trades', 'backtest_results', 'confidence_thresholds'
        ];
        
        // Get selected tables
        if (isset($_POST['tables']) && is_array($_POST['tables']) && count($_POST['tables']) > 0) {
            $tables_to_truncate = $_POST['tables'];
        } else {
            $tables_to_truncate = $all_tables;
        }
        
        // Disable foreign key checks
        $conn->query("SET FOREIGN_KEY_CHECKS = 0");
        
        $truncated_tables = [];
        $failed_tables = [];
        
        foreach ($tables_to_truncate as $table) {
            // Sanitize table name
            $table = $conn->real_escape_string($table);
            
            // Check if table exists
            $check_query = "SHOW TABLES LIKE '$table'";
            $result = $conn->query($check_query);
            
            if ($result && $result->num_rows > 0) {
                $truncate_query = "TRUNCATE TABLE `$table`";
                if ($conn->query($truncate_query)) {
                    $truncated_tables[] = $table;
                } else {
                    $failed_tables[] = $table . " (" . $conn->error . ")";
                }
            } else {
                $failed_tables[] = $table . " (Table does not exist)";
            }
        }
        
        // Re-enable foreign key checks
        $conn->query("SET FOREIGN_KEY_CHECKS = 1");
        
        if (count($truncated_tables) > 0) {
            $message = "Successfully truncated " . count($truncated_tables) . " tables.";
            $message_type = "success";
            
            if (count($failed_tables) > 0) {
                $message .= " Failed to truncate " . count($failed_tables) . " tables.";
                $message_type = "warning";
            }
        } else {
            $message = "No tables were truncated. Please select at least one table.";
            $message_type = "danger";
        }
        
        // Log the action
        logCleanupAction($conn, $truncated_tables, $failed_tables);
        
    } elseif (isset($_POST['confirm']) && $_POST['confirm'] === 'dry_run') {
        $message = "Dry run completed. No tables were actually truncated.";
        $message_type = "info";
        
        if (isset($_POST['tables']) && is_array($_POST['tables'])) {
            $dry_run_tables = $_POST['tables'];
            $message .= " Would truncate " . count($dry_run_tables) . " tables.";
        }
    }
}

// Get list of all tables for display
$tables_list = [];
$result = $conn->query("SHOW TABLES");
while ($row = $result->fetch_array()) {
    $tables_list[] = $row[0];
}

// Get row counts for each table
$table_stats = [];
foreach ($tables_list as $table) {
    $count_query = "SELECT COUNT(*) as count FROM `$table`";
    $count_result = $conn->query($count_query);
    if ($count_result) {
        $row = $count_result->fetch_assoc();
        $table_stats[$table] = $row['count'];
    } else {
        $table_stats[$table] = 0;
    }
}
?>

<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Crypto Bot - Database Cleanup Utility</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>
        body {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }
        .container-custom {
            max-width: 1200px;
            margin: 0 auto;
        }
        .card {
            border-radius: 15px;
            box-shadow: 0 10px 40px rgba(0,0,0,0.1);
            margin-bottom: 20px;
        }
        .card-header {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border-radius: 15px 15px 0 0 !important;
            padding: 20px;
        }
        .stats-card {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border-radius: 10px;
            padding: 15px;
            margin-bottom: 15px;
        }
        .warning-box {
            background-color: #fff3cd;
            border-left: 4px solid #ffc107;
            padding: 15px;
            border-radius: 8px;
            margin-bottom: 20px;
        }
        .table-hover tbody tr:hover {
            background-color: rgba(102, 126, 234, 0.1);
            cursor: pointer;
        }
        .table tbody tr.selected {
            background-color: rgba(102, 126, 234, 0.2);
            border-left: 3px solid #667eea;
        }
        footer {
            text-align: center;
            margin-top: 30px;
            color: white;
            opacity: 0.8;
        }
    </style>
</head>
<body>
<div class="container-custom">
    
    <!-- Header -->
    <div class="text-center mb-4">
        <h1 class="text-white">🗑️ Database Cleanup Utility</h1>
        <p class="text-white-50">Manage and clean your crypto trading database</p>
    </div>
    
    <!-- Alert Messages -->
    <?php if ($message): ?>
        <div class="alert alert-<?php echo $message_type; ?> alert-dismissible fade show" role="alert">
            <strong>
                <?php 
                if ($message_type === 'success') echo '✓ Success!';
                elseif ($message_type === 'warning') echo '⚠️ Warning!';
                elseif ($message_type === 'danger') echo '❌ Error!';
                else echo 'ℹ️ Info';
                ?>
            </strong> <?php echo htmlspecialchars($message); ?>
            <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
        </div>
    <?php endif; ?>
    
    <!-- Database Statistics -->
    <div class="row mb-4">
        <div class="col-md-3">
            <div class="stats-card">
                <h6 class="mb-2">📊 Total Tables</h6>
                <h2 class="mb-0"><?php echo count($tables_list); ?></h2>
                <small>in database</small>
            </div>
        </div>
        <div class="col-md-3">
            <div class="stats-card">
                <h6 class="mb-2">💾 Total Records</h6>
                <h2 class="mb-0"><?php echo number_format(array_sum($table_stats)); ?></h2>
                <small>across all tables</small>
            </div>
        </div>
        <div class="col-md-3">
            <div class="stats-card">
                <h6 class="mb-2">📈 Tables with Data</h6>
                <h2 class="mb-0"><?php echo count(array_filter($table_stats)); ?></h2>
                <small>non-empty tables</small>
            </div>
        </div>
        <div class="col-md-3">
            <div class="stats-card">
                <h6 class="mb-2">🕒 Last Cleanup</h6>
                <h2 class="mb-0">
                    <?php
                    $log_file = __DIR__ . '/cleanup_log.txt';
                    if (file_exists($log_file)) {
                        $lines = file($log_file);
                        if (!empty($lines)) {
                            $last_line = end($lines);
                            if (preg_match('/\[(.*?)\]/', $last_line, $matches)) {
                                echo date('M d', strtotime($matches[1]));
                            } else {
                                echo 'Never';
                            }
                        } else {
                            echo 'Never';
                        }
                    } else {
                        echo 'Never';
                    }
                    ?>
                </h2>
                <small>since last cleanup</small>
            </div>
        </div>
    </div>
    
    <!-- Warning Box -->
    <div class="warning-box">
        <strong>⚠️ DANGER ZONE</strong><br>
        <small>
            This action will permanently delete all data from the selected tables. 
            This operation cannot be undone. Please make sure you have a backup before proceeding.
            The bot will need to refetch data from exchanges after cleanup.
        </small>
    </div>
    
    <!-- Cleanup Form -->
    <div class="card">
        <div class="card-header">
            <h5 class="mb-0">🧹 Database Cleanup Options</h5>
        </div>
        <div class="card-body">
            <form method="POST" id="cleanupForm" onsubmit="return confirmCleanup()">
                <!-- Selection Controls -->
                <div class="mb-3">
                    <div class="btn-group" role="group">
                        <button type="button" class="btn btn-sm btn-outline-primary" onclick="selectAll()">✓ Select All</button>
                        <button type="button" class="btn btn-sm btn-outline-secondary" onclick="deselectAll()">✗ Deselect All</button>
                        <button type="button" class="btn btn-sm btn-outline-info" onclick="selectTablesWithData()">📊 Select Tables with Data</button>
                        <button type="button" class="btn btn-sm btn-outline-warning" onclick="selectPatternTables()">📈 Select Pattern Tables</button>
                    </div>
                </div>
                
                <!-- Tables List -->
                <div class="table-responsive" style="max-height: 500px; overflow-y: auto;">
                    <table class="table table-hover table-sm">
                        <thead class="table-dark">
                            <tr>
                                <th style="width: 40px;">
                                    <input type="checkbox" id="selectAllCheckbox" onchange="toggleAllCheckboxes(this)">
                                </th>
                                <th>Table Name</th>
                                <th>Records</th>
                                <th>Status</th>
                                <th>Description</th>
                            </tr>
                        </thead>
                        <tbody>
                            <?php foreach ($tables_list as $table): ?>
                                <?php 
                                $record_count = $table_stats[$table];
                                $has_data = $record_count > 0;
                                $table_type = getTableType($table);
                                ?>
                                <tr class="<?php echo $has_data ? 'table-warning' : ''; ?>" onclick="toggleRow(this, '<?php echo $table; ?>')">
                                    <td>
                                        <input type="checkbox" name="tables[]" value="<?php echo htmlspecialchars($table); ?>" 
                                               id="chk_<?php echo md5($table); ?>" class="table-checkbox">
                                    </td>
                                    <td>
                                        <code><?php echo htmlspecialchars($table); ?></code>
                                        <?php if ($has_data): ?>
                                            <span class="badge bg-warning text-dark ms-2">has data</span>
                                        <?php endif; ?>
                                    </td>
                                    <td class="table-count">
                                        <?php if ($record_count > 0): ?>
                                            <span class="badge bg-<?php echo $record_count > 10000 ? 'danger' : ($record_count > 1000 ? 'warning' : 'info'); ?>">
                                                <?php echo number_format($record_count); ?>
                                            </span>
                                        <?php else: ?>
                                            <span class="text-muted">empty</span>
                                        <?php endif; ?>
                                    </td>
                                    <td>
                                        <?php 
                                        $status_class = '';
                                        $status_text = '';
                                        switch($table_type) {
                                            case 'pattern':
                                                $status_class = 'info';
                                                $status_text = 'Pattern';
                                                break;
                                            case 'weight':
                                                $status_class = 'secondary';
                                                $status_text = 'Weight';
                                                break;
                                            case 'data':
                                                $status_class = 'primary';
                                                $status_text = 'OHLCV';
                                                break;
                                            case 'trading':
                                                $status_class = 'success';
                                                $status_text = 'Trading';
                                                break;
                                            default:
                                                $status_class = 'light';
                                                $status_text = 'Other';
                                        }
                                        ?>
                                        <span class="badge bg-<?php echo $status_class; ?>"><?php echo $status_text; ?></span>
                                    </td>
                                    <td>
                                        <small class="text-muted">
                                            <?php echo getTableDescription($table); ?>
                                        </small>
                                    </td>
                                </tr>
                            <?php endforeach; ?>
                        </tbody>
                    </table>
                </div>
                
                <!-- Action Buttons -->
                <div class="mt-4">
                    <div class="row">
                        <div class="col-md-6">
                            <button type="button" class="btn btn-warning w-100 mb-2" onclick="dryRun()">
                                🔍 Dry Run (Preview Only)
                            </button>
                        </div>
                        <div class="col-md-6">
                            <button type="submit" class="btn btn-danger w-100" id="cleanupBtn">
                                🗑️ Truncate Selected Tables
                            </button>
                        </div>
                    </div>
                </div>
                
                <!-- Hidden confirm field -->
                <input type="hidden" name="confirm" id="confirmField" value="">
            </form>
        </div>
    </div>
    
    <!-- Backup Recommendation -->
    <div class="card mt-3">
        <div class="card-header bg-info text-white">
            <h6 class="mb-0">💡 Recommendations</h6>
        </div>
        <div class="card-body">
            <ul class="mb-0">
                <li><strong>Before cleaning:</strong> Make sure to export any important data you want to keep</li>
                <li><strong>After cleaning:</strong> The bot will need to refetch OHLCV data and retrain patterns</li>
                <li><strong>Pattern tables:</strong> These store learned patterns - clearing them means retraining from scratch</li>
                <li><strong>OHLCV data:</strong> This is raw candle data - can be refetched from exchanges</li>
                <li><strong>Recommended order:</strong> First export data, then clean, then refetch and retrain</li>
            </ul>
        </div>
    </div>
    
    <!-- Recent Cleanup Log -->
    <?php
    $log_file = __DIR__ . '/cleanup_log.txt';
    if (file_exists($log_file) && filesize($log_file) > 0):
    ?>
    <div class="card mt-3">
        <div class="card-header bg-secondary text-white">
            <h6 class="mb-0">📜 Recent Cleanup Log</h6>
        </div>
        <div class="card-body">
            <pre style="max-height: 200px; overflow-y: auto; font-size: 12px;" class="bg-light p-2 rounded"><?php 
                echo htmlspecialchars(file_get_contents($log_file));
            ?></pre>
        </div>
    </div>
    <?php endif; ?>
    
    <footer>
        <small>⚠️ Use with caution. This action cannot be undone. Make sure you have backups!</small>
    </footer>
</div>

<script>
function toggleAllCheckboxes(source) {
    const checkboxes = document.querySelectorAll('.table-checkbox');
    checkboxes.forEach(checkbox => {
        checkbox.checked = source.checked;
    });
    updateRowSelection();
}

function toggleRow(row, tableName) {
    const checkbox = row.querySelector('.table-checkbox');
    if (checkbox) {
        checkbox.checked = !checkbox.checked;
        if (checkbox.checked) {
            row.classList.add('selected');
        } else {
            row.classList.remove('selected');
        }
    }
}

function updateRowSelection() {
    const rows = document.querySelectorAll('tbody tr');
    rows.forEach(row => {
        const checkbox = row.querySelector('.table-checkbox');
        if (checkbox && checkbox.checked) {
            row.classList.add('selected');
        } else if (checkbox) {
            row.classList.remove('selected');
        }
    });
}

function selectAll() {
    const checkboxes = document.querySelectorAll('.table-checkbox');
    checkboxes.forEach(checkbox => {
        checkbox.checked = true;
    });
    updateRowSelection();
    document.getElementById('selectAllCheckbox').checked = true;
}

function deselectAll() {
    const checkboxes = document.querySelectorAll('.table-checkbox');
    checkboxes.forEach(checkbox => {
        checkbox.checked = false;
    });
    updateRowSelection();
    document.getElementById('selectAllCheckbox').checked = false;
}

function selectTablesWithData() {
    const rows = document.querySelectorAll('tbody tr');
    rows.forEach(row => {
        const hasDataBadge = row.querySelector('.badge.bg-warning');
        const checkbox = row.querySelector('.table-checkbox');
        if (checkbox && hasDataBadge) {
            checkbox.checked = true;
            row.classList.add('selected');
        } else if (checkbox) {
            checkbox.checked = false;
            row.classList.remove('selected');
        }
    });
    document.getElementById('selectAllCheckbox').checked = false;
}

function selectPatternTables() {
    const rows = document.querySelectorAll('tbody tr');
    rows.forEach(row => {
        const patternBadge = row.querySelector('.badge.bg-info');
        const checkbox = row.querySelector('.table-checkbox');
        if (checkbox && patternBadge && patternBadge.textContent === 'Pattern') {
            checkbox.checked = true;
            row.classList.add('selected');
        } else if (checkbox) {
            checkbox.checked = false;
            row.classList.remove('selected');
        }
    });
    document.getElementById('selectAllCheckbox').checked = false;
}

function dryRun() {
    const selectedCheckboxes = document.querySelectorAll('.table-checkbox:checked');
    if (selectedCheckboxes.length === 0) {
        alert('Please select tables for dry run.');
        return;
    }
    
    const tableNames = Array.from(selectedCheckboxes).map(cb => cb.value);
    let message = `🔍 DRY RUN - Would truncate ${tableNames.length} table(s):\n\n`;
    message += tableNames.join('\n');
    message += `\n\nNo actual changes were made.`;
    
    alert(message);
    
    // Submit for dry run
    document.getElementById('confirmField').value = 'dry_run';
    document.getElementById('cleanupForm').submit();
}

function confirmCleanup() {
    const selectedCheckboxes = document.querySelectorAll('.table-checkbox:checked');
    if (selectedCheckboxes.length === 0) {
        alert('Please select at least one table to truncate.');
        return false;
    }
    
    const tableNames = Array.from(selectedCheckboxes).map(cb => cb.value);
    const tableCount = tableNames.length;
    const hasDataTables = Array.from(selectedCheckboxes).some(cb => {
        const row = cb.closest('tr');
        return row && row.querySelector('.badge.bg-warning');
    });
    
    let message = `⚠️ DANGER: This will permanently delete ALL data from ${tableCount} table(s):\n\n`;
    message += tableNames.slice(0, 10).join('\n');
    if (tableNames.length > 10) message += `\n... and ${tableNames.length - 10} more`;
    
    message += `\n\nThis action CANNOT be undone!\n`;
    
    if (hasDataTables) {
        message += `\n⚠️ Some selected tables contain data!\n`;
    }
    
    message += `\nType "CONFIRM" in the box below to proceed:`;
    
    const userInput = prompt(message);
    if (userInput === 'CONFIRM') {
        document.getElementById('confirmField').value = 'yes';
        const btn = document.getElementById('cleanupBtn');
        btn.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>Truncating...';
        btn.disabled = true;
        return true;
    }
    
    return false;
}

// Update row selection when checkboxes are clicked directly
document.addEventListener('DOMContentLoaded', function() {
    const checkboxes = document.querySelectorAll('.table-checkbox');
    checkboxes.forEach(checkbox => {
        checkbox.addEventListener('change', function() {
            const row = this.closest('tr');
            if (this.checked) {
                row.classList.add('selected');
            } else {
                row.classList.remove('selected');
            }
            
            // Update select all checkbox
            const allCheckboxes = document.querySelectorAll('.table-checkbox');
            const allChecked = Array.from(allCheckboxes).every(cb => cb.checked);
            document.getElementById('selectAllCheckbox').checked = allChecked;
        });
    });
});
</script>

<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>

<?php
$conn->close();
?>