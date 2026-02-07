-- phpMyAdmin SQL Dump
-- version 5.1.1
-- https://www.phpmyadmin.net/
--
-- Host: 127.0.0.1:3306
-- Generation Time: Feb 07, 2026 at 08:48 AM
-- Server version: 5.7.36
-- PHP Version: 7.4.26

SET SQL_MODE = "NO_AUTO_VALUE_ON_ZERO";
START TRANSACTION;
SET time_zone = "+00:00";


/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
/*!40101 SET @OLD_CHARACTER_SET_RESULTS=@@CHARACTER_SET_RESULTS */;
/*!40101 SET @OLD_COLLATION_CONNECTION=@@COLLATION_CONNECTION */;
/*!40101 SET NAMES utf8mb4 */;

--
-- Database: `crypto_data`
--

-- --------------------------------------------------------

--
-- Table structure for table `backtest_results`
--

DROP TABLE IF EXISTS `backtest_results`;
CREATE TABLE IF NOT EXISTS `backtest_results` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `symbol` varchar(50) NOT NULL,
  `timeframe` varchar(20) NOT NULL,
  `strategy_name` varchar(100) DEFAULT NULL,
  `total_trades` int(11) DEFAULT '0',
  `winning_trades` int(11) DEFAULT '0',
  `losing_trades` int(11) DEFAULT '0',
  `win_rate` double DEFAULT '0',
  `total_pnl` double DEFAULT '0',
  `sharpe_ratio` double DEFAULT '0',
  `max_drawdown` double DEFAULT '0',
  `parameters` json DEFAULT NULL,
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_symbol_timeframe` (`symbol`,`timeframe`),
  KEY `idx_created_at` (`created_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- --------------------------------------------------------

--
-- Table structure for table `binance_all_pairs`
--

DROP TABLE IF EXISTS `binance_all_pairs`;
CREATE TABLE IF NOT EXISTS `binance_all_pairs` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `symbol` varchar(50) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `base_asset` varchar(20) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `quote_asset` varchar(20) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `pair_type` enum('spot','future') COLLATE utf8mb4_unicode_ci DEFAULT 'spot',
  `status` enum('active','inactive') COLLATE utf8mb4_unicode_ci DEFAULT 'active',
  `last_updated` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `unique_pair` (`symbol`,`pair_type`),
  KEY `idx_symbol` (`symbol`),
  KEY `idx_pair_type` (`pair_type`),
  KEY `idx_status` (`status`)
) ENGINE=MyISAM DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- --------------------------------------------------------

--
-- Table structure for table `coin_categories`
--

DROP TABLE IF EXISTS `coin_categories`;
CREATE TABLE IF NOT EXISTS `coin_categories` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `symbol` varchar(100) NOT NULL,
  `base` varchar(50) DEFAULT NULL,
  `quote` varchar(50) DEFAULT NULL,
  `category` varchar(200) DEFAULT NULL,
  `source` enum('auto','manual') DEFAULT 'auto',
  `updated_at` datetime DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uniq_symbol` (`symbol`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- --------------------------------------------------------

--
-- Table structure for table `confidence_thresholds`
--

DROP TABLE IF EXISTS `confidence_thresholds`;
CREATE TABLE IF NOT EXISTS `confidence_thresholds` (
  `timeframe` varchar(20) NOT NULL,
  `perfect_pct` double DEFAULT '0',
  PRIMARY KEY (`timeframe`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 ROW_FORMAT=DYNAMIC;

-- --------------------------------------------------------

--
-- Table structure for table `daily_gainers`
--

DROP TABLE IF EXISTS `daily_gainers`;
CREATE TABLE IF NOT EXISTS `daily_gainers` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `symbol` varchar(50) NOT NULL,
  `price` double DEFAULT NULL,
  `price_change_percent` double DEFAULT NULL,
  `volume_24h` double DEFAULT NULL,
  `fetched_at` datetime DEFAULT CURRENT_TIMESTAMP,
  `fetch_date` date GENERATED ALWAYS AS (cast(`fetched_at` as date)) STORED,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uniq_symbol_today` (`symbol`,`fetched_at`),
  UNIQUE KEY `uniq_daily` (`symbol`,`fetch_date`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- --------------------------------------------------------

--
-- Table structure for table `daily_gainers_losers`
--

DROP TABLE IF EXISTS `daily_gainers_losers`;
CREATE TABLE IF NOT EXISTS `daily_gainers_losers` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `symbol` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL,
  `price` double DEFAULT NULL,
  `price_change_percent` double DEFAULT NULL,
  `volume_24h` double DEFAULT NULL,
  `fetched_at` datetime DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_gainers_symbol` (`symbol`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- --------------------------------------------------------

--
-- Table structure for table `exchange_symbols`
--

DROP TABLE IF EXISTS `exchange_symbols`;
CREATE TABLE IF NOT EXISTS `exchange_symbols` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `exchange` varchar(20) COLLATE utf8mb4_unicode_ci NOT NULL,
  `symbol` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL,
  `base` varchar(20) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `quote` varchar(20) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `active` tinyint(1) DEFAULT '1',
  `created_at` datetime DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uniq_exchange_symbol` (`exchange`,`symbol`),
  KEY `idx_exchange` (`exchange`),
  KEY `idx_symbol_search` (`symbol`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- --------------------------------------------------------

--
-- Table structure for table `ohlcv`
--

DROP TABLE IF EXISTS `ohlcv`;
CREATE TABLE IF NOT EXISTS `ohlcv` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `symbol` varchar(50) DEFAULT NULL,
  `timeframe` varchar(10) DEFAULT NULL,
  `timestamp` datetime DEFAULT NULL,
  `open` float DEFAULT NULL,
  `high` float DEFAULT NULL,
  `low` float DEFAULT NULL,
  `close` float DEFAULT NULL,
  `volume` float DEFAULT NULL,
  PRIMARY KEY (`id`)
) ENGINE=MyISAM DEFAULT CHARSET=latin1;

-- --------------------------------------------------------

--
-- Table structure for table `ohlcv_data`
--

DROP TABLE IF EXISTS `ohlcv_data`;
CREATE TABLE IF NOT EXISTS `ohlcv_data` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `symbol` varchar(20) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `timeframe` varchar(10) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `time_utc` datetime DEFAULT NULL,
  `open` double DEFAULT NULL,
  `high` double DEFAULT NULL,
  `low` double DEFAULT NULL,
  `close` double DEFAULT NULL,
  `volume` double DEFAULT NULL,
  `volume_diff` double DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `idx_ohlcv_symbol_tf` (`symbol`,`timeframe`),
  KEY `idx_symbol_timeframe_time` (`symbol`,`timeframe`,`time_utc`)
) ENGINE=MyISAM DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- --------------------------------------------------------

--
-- Table structure for table `ohlcv_data_superbot`
--

DROP TABLE IF EXISTS `ohlcv_data_superbot`;
CREATE TABLE IF NOT EXISTS `ohlcv_data_superbot` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `symbol` varchar(50) DEFAULT NULL,
  `timeframe` varchar(20) DEFAULT NULL,
  `time_utc` datetime DEFAULT NULL,
  `open` double DEFAULT NULL,
  `high` double DEFAULT NULL,
  `low` double DEFAULT NULL,
  `close` double DEFAULT NULL,
  `volume` double DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uniq_candle` (`symbol`,`timeframe`,`time_utc`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- --------------------------------------------------------

--
-- Table structure for table `patterns`
--

DROP TABLE IF EXISTS `patterns`;
CREATE TABLE IF NOT EXISTS `patterns` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `coin` varchar(50) DEFAULT NULL,
  `tf` varchar(20) DEFAULT NULL,
  `memory_str` text,
  `weight` float DEFAULT NULL,
  `high_weight` float DEFAULT NULL,
  `low_weight` float DEFAULT NULL,
  `created_at` datetime DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`)
) ENGINE=MyISAM DEFAULT CHARSET=latin1;

-- --------------------------------------------------------

--
-- Table structure for table `patterns_1d`
--

DROP TABLE IF EXISTS `patterns_1d`;
CREATE TABLE IF NOT EXISTS `patterns_1d` (
  `pattern_hash` varchar(64) NOT NULL,
  `pattern_string` text NOT NULL,
  `outcomes` json DEFAULT NULL,
  `occurrences` int(11) DEFAULT '1',
  `created_at` datetime DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`pattern_hash`),
  KEY `idx_updated` (`updated_at`),
  KEY `idx_occurrences` (`occurrences`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- --------------------------------------------------------

--
-- Table structure for table `patterns_1h`
--

DROP TABLE IF EXISTS `patterns_1h`;
CREATE TABLE IF NOT EXISTS `patterns_1h` (
  `pattern_hash` varchar(64) NOT NULL,
  `pattern_string` text NOT NULL,
  `outcomes` json DEFAULT NULL,
  `occurrences` int(11) DEFAULT '1',
  `created_at` datetime DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`pattern_hash`),
  KEY `idx_updated` (`updated_at`),
  KEY `idx_occurrences` (`occurrences`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- --------------------------------------------------------

--
-- Table structure for table `patterns_1m`
--

DROP TABLE IF EXISTS `patterns_1m`;
CREATE TABLE IF NOT EXISTS `patterns_1m` (
  `pattern_hash` varchar(64) NOT NULL,
  `pattern_string` text NOT NULL,
  `outcomes` json DEFAULT NULL,
  `occurrences` int(11) DEFAULT '1',
  `created_at` datetime DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`pattern_hash`),
  KEY `idx_updated` (`updated_at`),
  KEY `idx_occurrences` (`occurrences`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- --------------------------------------------------------

--
-- Table structure for table `patterns_4h`
--

DROP TABLE IF EXISTS `patterns_4h`;
CREATE TABLE IF NOT EXISTS `patterns_4h` (
  `pattern_hash` varchar(64) NOT NULL,
  `pattern_string` text NOT NULL,
  `outcomes` json DEFAULT NULL,
  `occurrences` int(11) DEFAULT '1',
  `created_at` datetime DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`pattern_hash`),
  KEY `idx_updated` (`updated_at`),
  KEY `idx_occurrences` (`occurrences`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- --------------------------------------------------------

--
-- Table structure for table `patterns_5m`
--

DROP TABLE IF EXISTS `patterns_5m`;
CREATE TABLE IF NOT EXISTS `patterns_5m` (
  `pattern_hash` varchar(64) NOT NULL,
  `pattern_string` text NOT NULL,
  `outcomes` json DEFAULT NULL,
  `occurrences` int(11) DEFAULT '1',
  `created_at` datetime DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`pattern_hash`),
  KEY `idx_updated` (`updated_at`),
  KEY `idx_occurrences` (`occurrences`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- --------------------------------------------------------

--
-- Table structure for table `patterns_15m`
--

DROP TABLE IF EXISTS `patterns_15m`;
CREATE TABLE IF NOT EXISTS `patterns_15m` (
  `pattern_hash` varchar(64) NOT NULL,
  `pattern_string` text NOT NULL,
  `outcomes` json DEFAULT NULL,
  `occurrences` int(11) DEFAULT '1',
  `created_at` datetime DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`pattern_hash`),
  KEY `idx_updated` (`updated_at`),
  KEY `idx_occurrences` (`occurrences`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- --------------------------------------------------------

--
-- Table structure for table `predictions_log`
--

DROP TABLE IF EXISTS `predictions_log`;
CREATE TABLE IF NOT EXISTS `predictions_log` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `symbol` varchar(20) DEFAULT NULL,
  `timeframe` varchar(10) DEFAULT NULL,
  `predicted_change` float DEFAULT NULL,
  `confidence` float DEFAULT NULL,
  `signal` varchar(20) DEFAULT NULL,
  `recommendation` varchar(50) DEFAULT NULL,
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  `actual_change` float DEFAULT NULL,
  `accuracy` float DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `idx_symbol_timeframe` (`symbol`,`timeframe`),
  KEY `idx_created_at` (`created_at`)
) ENGINE=MyISAM DEFAULT CHARSET=latin1;

-- --------------------------------------------------------

--
-- Table structure for table `realtime_trades`
--

DROP TABLE IF EXISTS `realtime_trades`;
CREATE TABLE IF NOT EXISTS `realtime_trades` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `exchange` varchar(50) NOT NULL,
  `symbol` varchar(50) NOT NULL,
  `price` double NOT NULL,
  `volume` double NOT NULL,
  `side` enum('buy','sell') NOT NULL,
  `timestamp_ms` bigint(20) NOT NULL,
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_exchange_symbol` (`exchange`,`symbol`),
  KEY `idx_timestamp` (`timestamp_ms`),
  KEY `idx_created` (`created_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- --------------------------------------------------------

--
-- Table structure for table `trades`
--

DROP TABLE IF EXISTS `trades`;
CREATE TABLE IF NOT EXISTS `trades` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `coin` varchar(50) DEFAULT NULL,
  `side` enum('buy','sell') DEFAULT NULL,
  `price` float DEFAULT NULL,
  `amount` float DEFAULT NULL,
  `timestamp` datetime DEFAULT NULL,
  `pnl` float DEFAULT '0',
  PRIMARY KEY (`id`)
) ENGINE=MyISAM DEFAULT CHARSET=latin1;

-- --------------------------------------------------------

--
-- Table structure for table `weights_close_1d`
--

DROP TABLE IF EXISTS `weights_close_1d`;
CREATE TABLE IF NOT EXISTS `weights_close_1d` (
  `pattern_hash` varchar(64) NOT NULL,
  `weight` double DEFAULT '1',
  `updated_at` datetime DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`pattern_hash`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- --------------------------------------------------------

--
-- Table structure for table `weights_close_1h`
--

DROP TABLE IF EXISTS `weights_close_1h`;
CREATE TABLE IF NOT EXISTS `weights_close_1h` (
  `pattern_hash` varchar(64) NOT NULL,
  `weight` double DEFAULT '1',
  `updated_at` datetime DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`pattern_hash`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- --------------------------------------------------------

--
-- Table structure for table `weights_close_1m`
--

DROP TABLE IF EXISTS `weights_close_1m`;
CREATE TABLE IF NOT EXISTS `weights_close_1m` (
  `pattern_hash` varchar(64) NOT NULL,
  `weight` double DEFAULT '1',
  `updated_at` datetime DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`pattern_hash`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- --------------------------------------------------------

--
-- Table structure for table `weights_close_4h`
--

DROP TABLE IF EXISTS `weights_close_4h`;
CREATE TABLE IF NOT EXISTS `weights_close_4h` (
  `pattern_hash` varchar(64) NOT NULL,
  `weight` double DEFAULT '1',
  `updated_at` datetime DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`pattern_hash`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- --------------------------------------------------------

--
-- Table structure for table `weights_close_5m`
--

DROP TABLE IF EXISTS `weights_close_5m`;
CREATE TABLE IF NOT EXISTS `weights_close_5m` (
  `pattern_hash` varchar(64) NOT NULL,
  `weight` double DEFAULT '1',
  `updated_at` datetime DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`pattern_hash`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- --------------------------------------------------------

--
-- Table structure for table `weights_close_15m`
--

DROP TABLE IF EXISTS `weights_close_15m`;
CREATE TABLE IF NOT EXISTS `weights_close_15m` (
  `pattern_hash` varchar(64) NOT NULL,
  `weight` double DEFAULT '1',
  `updated_at` datetime DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`pattern_hash`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- --------------------------------------------------------

--
-- Table structure for table `weights_high_1d`
--

DROP TABLE IF EXISTS `weights_high_1d`;
CREATE TABLE IF NOT EXISTS `weights_high_1d` (
  `pattern_hash` varchar(64) NOT NULL,
  `weight` double DEFAULT '1',
  `updated_at` datetime DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`pattern_hash`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- --------------------------------------------------------

--
-- Table structure for table `weights_high_1h`
--

DROP TABLE IF EXISTS `weights_high_1h`;
CREATE TABLE IF NOT EXISTS `weights_high_1h` (
  `pattern_hash` varchar(64) NOT NULL,
  `weight` double DEFAULT '1',
  `updated_at` datetime DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`pattern_hash`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- --------------------------------------------------------

--
-- Table structure for table `weights_high_1m`
--

DROP TABLE IF EXISTS `weights_high_1m`;
CREATE TABLE IF NOT EXISTS `weights_high_1m` (
  `pattern_hash` varchar(64) NOT NULL,
  `weight` double DEFAULT '1',
  `updated_at` datetime DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`pattern_hash`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- --------------------------------------------------------

--
-- Table structure for table `weights_high_4h`
--

DROP TABLE IF EXISTS `weights_high_4h`;
CREATE TABLE IF NOT EXISTS `weights_high_4h` (
  `pattern_hash` varchar(64) NOT NULL,
  `weight` double DEFAULT '1',
  `updated_at` datetime DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`pattern_hash`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- --------------------------------------------------------

--
-- Table structure for table `weights_high_5m`
--

DROP TABLE IF EXISTS `weights_high_5m`;
CREATE TABLE IF NOT EXISTS `weights_high_5m` (
  `pattern_hash` varchar(64) NOT NULL,
  `weight` double DEFAULT '1',
  `updated_at` datetime DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`pattern_hash`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- --------------------------------------------------------

--
-- Table structure for table `weights_high_15m`
--

DROP TABLE IF EXISTS `weights_high_15m`;
CREATE TABLE IF NOT EXISTS `weights_high_15m` (
  `pattern_hash` varchar(64) NOT NULL,
  `weight` double DEFAULT '1',
  `updated_at` datetime DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`pattern_hash`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- --------------------------------------------------------

--
-- Table structure for table `weights_low_1d`
--

DROP TABLE IF EXISTS `weights_low_1d`;
CREATE TABLE IF NOT EXISTS `weights_low_1d` (
  `pattern_hash` varchar(64) NOT NULL,
  `weight` double DEFAULT '1',
  `updated_at` datetime DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`pattern_hash`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- --------------------------------------------------------

--
-- Table structure for table `weights_low_1h`
--

DROP TABLE IF EXISTS `weights_low_1h`;
CREATE TABLE IF NOT EXISTS `weights_low_1h` (
  `pattern_hash` varchar(64) NOT NULL,
  `weight` double DEFAULT '1',
  `updated_at` datetime DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`pattern_hash`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- --------------------------------------------------------

--
-- Table structure for table `weights_low_1m`
--

DROP TABLE IF EXISTS `weights_low_1m`;
CREATE TABLE IF NOT EXISTS `weights_low_1m` (
  `pattern_hash` varchar(64) NOT NULL,
  `weight` double DEFAULT '1',
  `updated_at` datetime DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`pattern_hash`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- --------------------------------------------------------

--
-- Table structure for table `weights_low_4h`
--

DROP TABLE IF EXISTS `weights_low_4h`;
CREATE TABLE IF NOT EXISTS `weights_low_4h` (
  `pattern_hash` varchar(64) NOT NULL,
  `weight` double DEFAULT '1',
  `updated_at` datetime DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`pattern_hash`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- --------------------------------------------------------

--
-- Table structure for table `weights_low_5m`
--

DROP TABLE IF EXISTS `weights_low_5m`;
CREATE TABLE IF NOT EXISTS `weights_low_5m` (
  `pattern_hash` varchar(64) NOT NULL,
  `weight` double DEFAULT '1',
  `updated_at` datetime DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`pattern_hash`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- --------------------------------------------------------

--
-- Table structure for table `weights_low_15m`
--

DROP TABLE IF EXISTS `weights_low_15m`;
CREATE TABLE IF NOT EXISTS `weights_low_15m` (
  `pattern_hash` varchar(64) NOT NULL,
  `weight` double DEFAULT '1',
  `updated_at` datetime DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`pattern_hash`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

--
-- Constraints for dumped tables
--

--
-- Constraints for table `weights_close_1d`
--
ALTER TABLE `weights_close_1d`
  ADD CONSTRAINT `weights_close_1d_ibfk_1` FOREIGN KEY (`pattern_hash`) REFERENCES `patterns_1d` (`pattern_hash`) ON DELETE CASCADE;

--
-- Constraints for table `weights_close_1h`
--
ALTER TABLE `weights_close_1h`
  ADD CONSTRAINT `weights_close_1h_ibfk_1` FOREIGN KEY (`pattern_hash`) REFERENCES `patterns_1h` (`pattern_hash`) ON DELETE CASCADE;

--
-- Constraints for table `weights_close_1m`
--
ALTER TABLE `weights_close_1m`
  ADD CONSTRAINT `weights_close_1m_ibfk_1` FOREIGN KEY (`pattern_hash`) REFERENCES `patterns_1m` (`pattern_hash`) ON DELETE CASCADE;

--
-- Constraints for table `weights_close_4h`
--
ALTER TABLE `weights_close_4h`
  ADD CONSTRAINT `weights_close_4h_ibfk_1` FOREIGN KEY (`pattern_hash`) REFERENCES `patterns_4h` (`pattern_hash`) ON DELETE CASCADE;

--
-- Constraints for table `weights_close_5m`
--
ALTER TABLE `weights_close_5m`
  ADD CONSTRAINT `weights_close_5m_ibfk_1` FOREIGN KEY (`pattern_hash`) REFERENCES `patterns_5m` (`pattern_hash`) ON DELETE CASCADE;

--
-- Constraints for table `weights_close_15m`
--
ALTER TABLE `weights_close_15m`
  ADD CONSTRAINT `weights_close_15m_ibfk_1` FOREIGN KEY (`pattern_hash`) REFERENCES `patterns_15m` (`pattern_hash`) ON DELETE CASCADE;

--
-- Constraints for table `weights_high_1d`
--
ALTER TABLE `weights_high_1d`
  ADD CONSTRAINT `weights_high_1d_ibfk_1` FOREIGN KEY (`pattern_hash`) REFERENCES `patterns_1d` (`pattern_hash`) ON DELETE CASCADE;

--
-- Constraints for table `weights_high_1h`
--
ALTER TABLE `weights_high_1h`
  ADD CONSTRAINT `weights_high_1h_ibfk_1` FOREIGN KEY (`pattern_hash`) REFERENCES `patterns_1h` (`pattern_hash`) ON DELETE CASCADE;

--
-- Constraints for table `weights_high_1m`
--
ALTER TABLE `weights_high_1m`
  ADD CONSTRAINT `weights_high_1m_ibfk_1` FOREIGN KEY (`pattern_hash`) REFERENCES `patterns_1m` (`pattern_hash`) ON DELETE CASCADE;

--
-- Constraints for table `weights_high_4h`
--
ALTER TABLE `weights_high_4h`
  ADD CONSTRAINT `weights_high_4h_ibfk_1` FOREIGN KEY (`pattern_hash`) REFERENCES `patterns_4h` (`pattern_hash`) ON DELETE CASCADE;

--
-- Constraints for table `weights_high_5m`
--
ALTER TABLE `weights_high_5m`
  ADD CONSTRAINT `weights_high_5m_ibfk_1` FOREIGN KEY (`pattern_hash`) REFERENCES `patterns_5m` (`pattern_hash`) ON DELETE CASCADE;

--
-- Constraints for table `weights_high_15m`
--
ALTER TABLE `weights_high_15m`
  ADD CONSTRAINT `weights_high_15m_ibfk_1` FOREIGN KEY (`pattern_hash`) REFERENCES `patterns_15m` (`pattern_hash`) ON DELETE CASCADE;

--
-- Constraints for table `weights_low_1d`
--
ALTER TABLE `weights_low_1d`
  ADD CONSTRAINT `weights_low_1d_ibfk_1` FOREIGN KEY (`pattern_hash`) REFERENCES `patterns_1d` (`pattern_hash`) ON DELETE CASCADE;

--
-- Constraints for table `weights_low_1h`
--
ALTER TABLE `weights_low_1h`
  ADD CONSTRAINT `weights_low_1h_ibfk_1` FOREIGN KEY (`pattern_hash`) REFERENCES `patterns_1h` (`pattern_hash`) ON DELETE CASCADE;

--
-- Constraints for table `weights_low_1m`
--
ALTER TABLE `weights_low_1m`
  ADD CONSTRAINT `weights_low_1m_ibfk_1` FOREIGN KEY (`pattern_hash`) REFERENCES `patterns_1m` (`pattern_hash`) ON DELETE CASCADE;

--
-- Constraints for table `weights_low_4h`
--
ALTER TABLE `weights_low_4h`
  ADD CONSTRAINT `weights_low_4h_ibfk_1` FOREIGN KEY (`pattern_hash`) REFERENCES `patterns_4h` (`pattern_hash`) ON DELETE CASCADE;

--
-- Constraints for table `weights_low_5m`
--
ALTER TABLE `weights_low_5m`
  ADD CONSTRAINT `weights_low_5m_ibfk_1` FOREIGN KEY (`pattern_hash`) REFERENCES `patterns_5m` (`pattern_hash`) ON DELETE CASCADE;

--
-- Constraints for table `weights_low_15m`
--
ALTER TABLE `weights_low_15m`
  ADD CONSTRAINT `weights_low_15m_ibfk_1` FOREIGN KEY (`pattern_hash`) REFERENCES `patterns_15m` (`pattern_hash`) ON DELETE CASCADE;
COMMIT;

/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
/*!40101 SET CHARACTER_SET_RESULTS=@OLD_CHARACTER_SET_RESULTS */;
/*!40101 SET COLLATION_CONNECTION=@OLD_COLLATION_CONNECTION */;
