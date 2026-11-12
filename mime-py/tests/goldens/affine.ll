define i64 @"$affine"(i64 %input) {
  %"$double" = add i64 %input, %input
  %"$triple" = add i64 %"$double", %input
  %"$result" = add i64 %"$triple", 1
  ret i64 %"$result"
}
