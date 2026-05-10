<?php

declare(strict_types=1);

use Smarty\Smarty;

require_once __DIR__ . '/../vendor/autoload.php';

$baseDir = dirname(__DIR__);

$smarty = new Smarty();
$smarty->setTemplateDir($baseDir . '/templates');
$smarty->setCompileDir($baseDir . '/templates_c');
$smarty->setCacheDir($baseDir . '/cache');
$smarty->setConfigDir($baseDir . '/config');
$smarty->error_unassigned = true;

return $smarty;
