define internal i64 @mime.w1(i64 %w0) {
  %v0 = add i64 %w0, %w0
  %v1 = add i64 %v0, %w0
  %v2 = add i64 %v1, 1
  ret i64 %v2
}
