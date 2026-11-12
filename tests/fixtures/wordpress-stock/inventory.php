<?php
function audit3_stock_reserve(int $stock, int $quantity) {
    if ($stock < 0 || $quantity <= 0 || $quantity > $stock) {
        return new WP_Error('audit3_stock_invalid', 'Invalid reservation.');
    }
    return $stock + $quantity;
}
