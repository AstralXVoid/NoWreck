<?php
$show = true;
$title = 'Home';
$body = '<p>Hi</p>';
?>
<!DOCTYPE html>
<html>
  <head>
    <title><?= page_title($title) ?></title>
  </head>
  <body>
    <?php if ($show): ?>
      <p><?= escape($body) ?></p>
    <?php endif; ?>
    <?php include 'nav.php'; ?>
  </body>
</html>
