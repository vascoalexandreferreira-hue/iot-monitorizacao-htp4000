-- MySQL Workbench Forward Engineering

SET @OLD_UNIQUE_CHECKS=@@UNIQUE_CHECKS, UNIQUE_CHECKS=0;
SET @OLD_FOREIGN_KEY_CHECKS=@@FOREIGN_KEY_CHECKS, FOREIGN_KEY_CHECKS=0;
SET @OLD_SQL_MODE=@@SQL_MODE, SQL_MODE='ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION';

-- -----------------------------------------------------
-- Schema mydb
-- -----------------------------------------------------
-- -----------------------------------------------------
-- Schema iot_sensores
-- -----------------------------------------------------

-- -----------------------------------------------------
-- Schema iot_sensores
-- -----------------------------------------------------
CREATE SCHEMA IF NOT EXISTS `iot_sensores` DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci ;
USE `iot_sensores` ;

-- -----------------------------------------------------
-- Table `iot_sensores`.`alertas`
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS `iot_sensores`.`alertas` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `device_id` VARCHAR(50) NOT NULL,
  `topico` VARCHAR(100) NOT NULL,
  `nivel` ENUM('AVISO', 'CRITICO') NOT NULL,
  `mensagem` VARCHAR(255) NOT NULL,
  `valor` FLOAT NOT NULL,
  `limiar` FLOAT NOT NULL,
  `resolvido` TINYINT(1) NULL DEFAULT '0',
  `criado_em` DATETIME NULL DEFAULT CURRENT_TIMESTAMP,
  `resolvido_em` DATETIME NULL DEFAULT NULL,
  `resolvido_por` VARCHAR(100) NULL DEFAULT NULL,
  PRIMARY KEY (`id`))
ENGINE = InnoDB
AUTO_INCREMENT = 515
DEFAULT CHARACTER SET = utf8mb4
COLLATE = utf8mb4_0900_ai_ci;


-- -----------------------------------------------------
-- Table `iot_sensores`.`leituras_sensores`
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS `iot_sensores`.`leituras_sensores` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `device_id` VARCHAR(50) NOT NULL,
  `topico` VARCHAR(100) NOT NULL,
  `temperatura` FLOAT NULL DEFAULT NULL,
  `rms_mm_s` FLOAT NULL DEFAULT NULL,
  `freq_hz` FLOAT NULL DEFAULT NULL,
  `amplitude` FLOAT NULL DEFAULT NULL,
  `corrente_A` FLOAT NULL DEFAULT NULL,
  `thd_pct` FLOAT NULL DEFAULT NULL,
  `fator_potencia` FLOAT NULL DEFAULT NULL,
  `status` VARCHAR(20) NULL DEFAULT NULL,
  `timestamp_sensor` DATETIME NOT NULL,
  `criado_em` DATETIME NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`))
ENGINE = InnoDB
AUTO_INCREMENT = 82264
DEFAULT CHARACTER SET = utf8mb4
COLLATE = utf8mb4_0900_ai_ci;


SET SQL_MODE=@OLD_SQL_MODE;
SET FOREIGN_KEY_CHECKS=@OLD_FOREIGN_KEY_CHECKS;
SET UNIQUE_CHECKS=@OLD_UNIQUE_CHECKS;
