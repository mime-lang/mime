define i64 @sum(i64 %w0) {
entry:
  %v0 = icmp eq i64 %w0, 0
  br i1 %v0, label %b0, label %b1
b0:
  ret i64 0
b1:
  %v1 = sub i64 %w0, 1
  %v2 = call i64 @sum(i64 %v1)
  %v3 = add i64 %v2, %w0
  ret i64 %v3
}

define i64 @forever(i64 %w0) {
  %v0 = call i64 @forever(i64 %w0)
  ret i64 %v0
}
