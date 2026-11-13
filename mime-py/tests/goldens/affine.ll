define i64 @"mime.affine"(i64 %"@number") {
  %"%double" = add i64 %"@number", %"@number"
  %"%triple" = add i64 %"%double", %"@number"
  %"%result" = add i64 %"%triple", 1
  ret i64 %"%result"
}
