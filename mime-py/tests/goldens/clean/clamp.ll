define i64 @clamp(i64 %w0, i64 %w1, i64 %w2) {
entry:
  %v0 = icmp slt i64 %w0, %w1
  br i1 %v0, label %b0, label %b1
b1:
  %v1 = icmp sgt i64 %w0, %w2
  br i1 %v1, label %b2, label %b3
b0:
  ret i64 %w1
b2:
  ret i64 %w2
b3:
  ret i64 %w0
}
