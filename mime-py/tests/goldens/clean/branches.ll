define i64 @sum(i64 %w0) {
entry:
  br label %b0
b0:
  %v0 = phi i64 [ 0, %entry ], [ %v3, %b0 ]
  %v1 = phi i64 [ 0, %entry ], [ %v4, %b0 ]
  %v2 = icmp sgt i64 %v0, %w0
  %v3 = add i64 %v0, 1
  %v4 = add i64 %v1, %v0
  br i1 %v2, label %b1, label %b0
b1:
  ret i64 %v1
}

define i1 @positive(i64 %w0) {
  %v0 = icmp sgt i64 %w0, 0
  ret i1 %v0
}

define i64 @pick(i1 %w1) {
entry:
  br i1 %w1, label %entry.e0, label %entry.e1
entry.e0:
  br label %b0
entry.e1:
  br label %b0
b0:
  %v0 = phi i64 [ 1, %entry.e0 ], [ 2, %entry.e1 ]
  ret i64 %v0
}

define i1 @negate(i1 %w1) {
entry:
  br i1 %w1, label %entry.e0, label %entry.e1
entry.e0:
  br label %b0
entry.e1:
  br label %b0
b0:
  %v0 = phi i1 [ false, %entry.e0 ], [ true, %entry.e1 ]
  ret i1 %v0
}
