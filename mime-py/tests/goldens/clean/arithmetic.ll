define i64 @square(i64 %w0) {
  %v0 = mul i64 %w0, %w0
  ret i64 %v0
}

define i64 @less(i64 %w0) {
  %v0 = sub i64 %w0, 1
  ret i64 %v0
}

define i64 @negate(i64 %w0) {
  %v0 = sub i64 0, %w0
  ret i64 %v0
}

define i64 @sum(i64 %w0) {
  %v0 = add i64 %w0, -9223372036854775808
  ret i64 %v0
}

define i64 @difference(i64 %w1, i64 %w2) {
  %v0 = sub i64 %w1, %w2
  ret i64 %v0
}

define i64 @seven() {
  ret i64 7
}
