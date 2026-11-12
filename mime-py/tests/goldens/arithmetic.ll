define i64 @"$square"(i64 %input) {
  %"$p" = mul i64 %input, %input
  ret i64 %"$p"
}

define i64 @"$less"(i64 %input) {
  %"$d" = sub i64 %input, 1
  ret i64 %"$d"
}

define i64 @"$negate"(i64 %input) {
  %"$n" = sub i64 0, %input
  ret i64 %"$n"
}

define i64 @"$sum"(i64 %input) {
  %"$total" = add i64 %input, -9223372036854775808
  ret i64 %"$total"
}

define i64 @"$seven"(i64 %input) {
  ret i64 7
}
