/// Compute the start index for tailing `count` lines from a total of `total` lines.
pub fn tail_start_index(total: usize, count: usize) -> usize {
    total.saturating_sub(count)
}
