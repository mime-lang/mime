# Shortest window with k distinct values

Write a function `solve(list<i64>, i64) -> i64`.

Call the arguments xs and k. A window is a contiguous run of one or more elements of xs. Return the length of the shortest window that contains at least k distinct values.

- If k <= 0, return 0.
- If no window has k distinct values, return -1. This includes an empty xs with k >= 1.
