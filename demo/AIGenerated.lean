/-
  Simulated AI-generated proof file.

  This is the kind of output you get when asking an LLM to "prove these theorems
  in Lean 4." The AI fills in what it can, leaves sorry where it cannot, and the
  file compiles clean. Nothing tells you the guarantees are hollow.
-/

-- Helper the AI got right
theorem list_length_nonneg (l : List Nat) : 0 ≤ l.length := by
  omega

-- The AI used sorry for the inductive step it couldn't figure out
theorem list_reverse_length (l : List Nat) : l.reverse.length = l.length := by
  induction l with
  | nil => simp
  | cons h t ih =>
    sorry  -- AI: "I'll fill this in later"

-- This one the AI proved using native_decide to avoid thinking about it
theorem small_prime : Nat.Prime 17 := by
  native_decide

-- Looks completely proved - no sorry visible here
-- But it depends on list_reverse_length above, which is tainted
theorem reverse_preserves_length_doubled (l : List Nat) :
    (l.reverse ++ l).length = 2 * l.length := by
  have h := list_reverse_length l
  simp [List.length_append, h]
  omega

-- The AI introduced Classical.choice unnecessarily to avoid constructing a witness
theorem exists_nat_gt (n : Nat) : ∃ m, n < m := by
  exact ⟨n + 1, Nat.lt_succ_self n⟩

-- Safe: standard arithmetic
theorem add_comm_example (a b : Nat) : a + b = b + a := by
  omega

-- The AI completely gave up here
theorem hard_number_theory (n : Nat) (h : n > 1) :
    ∃ p, Nat.Prime p ∧ p ∣ n := by
  sorry  -- AI: "This requires Nat.exists_prime_and_dvd, leaving for now"

-- Downstream of hard_number_theory - also tainted, invisibly
theorem composite_has_factor (n : Nat) (h1 : n > 1) (h2 : ¬ Nat.Prime n) :
    ∃ d, 1 < d ∧ d < n ∧ d ∣ n := by
  obtain ⟨p, hp, hdvd⟩ := hard_number_theory n h1
  sorry  -- depends on the sorry above
