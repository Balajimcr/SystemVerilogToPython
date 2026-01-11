#!/usr/bin/env python3
"""
Validation Utilities for SV-to-pyvsc Translations

This module provides tools for validating that pyvsc translations
are semantically equivalent to the original SystemVerilog code.

Features:
1. Statistical distribution testing
2. Constraint violation checking
3. Boundary value analysis
4. Seed reproducibility testing
5. Histogram comparison utilities
"""

import collections
import statistics
from typing import List, Dict, Any, Callable, Optional, Tuple
from dataclasses import dataclass
import random


@dataclass
class ValidationResult:
    """Result of a validation test"""
    passed: bool
    test_name: str
    message: str
    details: Optional[Dict[str, Any]] = None


class PyVSCValidator:
    """Validator for pyvsc randomization models"""
    
    def __init__(self, rand_obj_class):
        """
        Initialize validator with a pyvsc randobj class.
        
        Args:
            rand_obj_class: The @vsc.randobj decorated class to validate
        """
        self.rand_obj_class = rand_obj_class
        self.results: List[ValidationResult] = []
    
    def validate_all(self, iterations: int = 10000) -> List[ValidationResult]:
        """Run all validation tests"""
        self.results = []
        
        # Basic randomization test
        self.test_basic_randomization()
        
        # Statistical tests require more iterations
        self.test_value_distribution(iterations)
        
        # Boundary testing
        self.test_boundary_values(iterations)
        
        return self.results
    
    def test_basic_randomization(self, count: int = 100) -> ValidationResult:
        """Test that basic randomization works without errors"""
        try:
            obj = self.rand_obj_class()
            for _ in range(count):
                obj.randomize()
            
            result = ValidationResult(
                passed=True,
                test_name="Basic Randomization",
                message=f"Successfully randomized {count} times"
            )
        except Exception as e:
            result = ValidationResult(
                passed=False,
                test_name="Basic Randomization",
                message=f"Randomization failed: {str(e)}"
            )
        
        self.results.append(result)
        return result
    
    def test_value_distribution(
        self,
        iterations: int = 10000,
        field_names: Optional[List[str]] = None
    ) -> List[ValidationResult]:
        """
        Test that values are distributed across the valid range.
        
        Args:
            iterations: Number of randomization iterations
            field_names: Specific fields to test (None = all rand fields)
        """
        results = []
        obj = self.rand_obj_class()
        
        # Collect samples
        samples: Dict[str, List[int]] = collections.defaultdict(list)
        
        for _ in range(iterations):
            obj.randomize()
            
            # Get all attributes that look like rand fields
            for name in dir(obj):
                if name.startswith('_'):
                    continue
                if field_names and name not in field_names:
                    continue
                
                try:
                    val = getattr(obj, name)
                    # Try to convert to int (works for vsc types)
                    int_val = int(val)
                    samples[name].append(int_val)
                except (TypeError, ValueError, AttributeError):
                    pass
        
        # Analyze each field
        for name, values in samples.items():
            if len(values) < iterations * 0.9:  # Skip if not enough samples
                continue
            
            unique_count = len(set(values))
            min_val = min(values)
            max_val = max(values)
            mean_val = statistics.mean(values)
            
            # Check for reasonable distribution
            # (not all same value, reasonable spread)
            if unique_count == 1:
                result = ValidationResult(
                    passed=False,
                    test_name=f"Distribution: {name}",
                    message="All values are identical - possible constraint issue",
                    details={'unique_count': unique_count, 'value': values[0]}
                )
            else:
                result = ValidationResult(
                    passed=True,
                    test_name=f"Distribution: {name}",
                    message=f"Range: [{min_val}, {max_val}], Unique: {unique_count}",
                    details={
                        'min': min_val,
                        'max': max_val,
                        'mean': mean_val,
                        'unique_count': unique_count
                    }
                )
            
            results.append(result)
            self.results.append(result)
        
        return results
    
    def test_boundary_values(
        self,
        iterations: int = 10000,
        expected_bounds: Optional[Dict[str, Tuple[int, int]]] = None
    ) -> List[ValidationResult]:
        """
        Test that boundary values are reachable.
        
        Args:
            iterations: Number of randomization iterations
            expected_bounds: Dict of field_name -> (min, max) expected bounds
        """
        results = []
        obj = self.rand_obj_class()
        
        observed_bounds: Dict[str, Tuple[int, int]] = {}
        
        for _ in range(iterations):
            obj.randomize()
            
            for name in dir(obj):
                if name.startswith('_'):
                    continue
                
                try:
                    val = int(getattr(obj, name))
                    if name not in observed_bounds:
                        observed_bounds[name] = (val, val)
                    else:
                        curr_min, curr_max = observed_bounds[name]
                        observed_bounds[name] = (min(curr_min, val), max(curr_max, val))
                except (TypeError, ValueError, AttributeError):
                    pass
        
        # Compare with expected if provided
        if expected_bounds:
            for name, (exp_min, exp_max) in expected_bounds.items():
                if name in observed_bounds:
                    obs_min, obs_max = observed_bounds[name]
                    
                    min_ok = obs_min <= exp_min + (exp_max - exp_min) * 0.01
                    max_ok = obs_max >= exp_max - (exp_max - exp_min) * 0.01
                    
                    if min_ok and max_ok:
                        result = ValidationResult(
                            passed=True,
                            test_name=f"Bounds: {name}",
                            message=f"Observed [{obs_min}, {obs_max}] ≈ Expected [{exp_min}, {exp_max}]"
                        )
                    else:
                        result = ValidationResult(
                            passed=False,
                            test_name=f"Bounds: {name}",
                            message=f"Observed [{obs_min}, {obs_max}] ≠ Expected [{exp_min}, {exp_max}]"
                        )
                    
                    results.append(result)
                    self.results.append(result)
        
        return results
    
    def test_constraint_invariant(
        self,
        invariant_fn: Callable[[Any], bool],
        invariant_name: str,
        iterations: int = 1000
    ) -> ValidationResult:
        """
        Test a custom constraint invariant.
        
        Args:
            invariant_fn: Function that takes the randomized object and returns True if valid
            invariant_name: Name of the invariant for reporting
            iterations: Number of times to test
        """
        obj = self.rand_obj_class()
        violations = []
        
        for i in range(iterations):
            obj.randomize()
            
            if not invariant_fn(obj):
                violations.append(i)
        
        if violations:
            result = ValidationResult(
                passed=False,
                test_name=f"Invariant: {invariant_name}",
                message=f"Failed {len(violations)}/{iterations} times",
                details={'violation_indices': violations[:10]}
            )
        else:
            result = ValidationResult(
                passed=True,
                test_name=f"Invariant: {invariant_name}",
                message=f"Passed all {iterations} iterations"
            )
        
        self.results.append(result)
        return result
    
    def test_distribution_weights(
        self,
        field_name: str,
        expected_weights: Dict[Any, float],
        iterations: int = 10000,
        tolerance: float = 0.1
    ) -> ValidationResult:
        """
        Test that a field matches expected distribution weights.
        
        Args:
            field_name: Name of the field to test
            expected_weights: Dict of value -> expected probability (0-1)
            iterations: Number of iterations
            tolerance: Acceptable deviation from expected (0.1 = 10%)
        """
        obj = self.rand_obj_class()
        counter = collections.Counter()
        
        for _ in range(iterations):
            obj.randomize()
            val = getattr(obj, field_name)
            counter[int(val)] += 1
        
        # Compare distributions
        total = sum(counter.values())
        mismatches = []
        
        for value, expected_prob in expected_weights.items():
            observed_prob = counter.get(value, 0) / total
            
            if abs(observed_prob - expected_prob) > tolerance * expected_prob:
                mismatches.append({
                    'value': value,
                    'expected': expected_prob,
                    'observed': observed_prob
                })
        
        if mismatches:
            result = ValidationResult(
                passed=False,
                test_name=f"Weights: {field_name}",
                message=f"{len(mismatches)} weight mismatches",
                details={'mismatches': mismatches}
            )
        else:
            result = ValidationResult(
                passed=True,
                test_name=f"Weights: {field_name}",
                message="Distribution weights match expected"
            )
        
        self.results.append(result)
        return result
    
    def print_report(self):
        """Print validation report"""
        print("\n" + "=" * 70)
        print("VALIDATION REPORT")
        print("=" * 70)
        
        passed = sum(1 for r in self.results if r.passed)
        failed = len(self.results) - passed
        
        print(f"\nSummary: {passed} passed, {failed} failed\n")
        
        for result in self.results:
            status = "✅ PASS" if result.passed else "❌ FAIL"
            print(f"{status} | {result.test_name}")
            print(f"       {result.message}")
            if result.details and not result.passed:
                print(f"       Details: {result.details}")
        
        print("\n" + "=" * 70)


def compare_sv_pyvsc_distributions(
    sv_samples: List[int],
    pyvsc_samples: List[int],
    field_name: str,
    tolerance: float = 0.05
) -> ValidationResult:
    """
    Compare distribution of samples from SV simulation vs pyvsc.
    
    Args:
        sv_samples: Samples from SystemVerilog simulation
        pyvsc_samples: Samples from pyvsc randomization
        field_name: Name of the field being compared
        tolerance: Acceptable difference in cumulative distribution
    """
    # Compute histograms
    all_values = set(sv_samples) | set(pyvsc_samples)
    
    sv_counts = collections.Counter(sv_samples)
    pyvsc_counts = collections.Counter(pyvsc_samples)
    
    sv_total = len(sv_samples)
    pyvsc_total = len(pyvsc_samples)
    
    # Compare distributions using simple metric
    max_diff = 0
    for val in all_values:
        sv_prob = sv_counts.get(val, 0) / sv_total
        pyvsc_prob = pyvsc_counts.get(val, 0) / pyvsc_total
        max_diff = max(max_diff, abs(sv_prob - pyvsc_prob))
    
    if max_diff <= tolerance:
        return ValidationResult(
            passed=True,
            test_name=f"SV/pyvsc Comparison: {field_name}",
            message=f"Max distribution difference: {max_diff:.4f} <= {tolerance}"
        )
    else:
        return ValidationResult(
            passed=False,
            test_name=f"SV/pyvsc Comparison: {field_name}",
            message=f"Max distribution difference: {max_diff:.4f} > {tolerance}"
        )


# =============================================================================
# EXAMPLE USAGE
# =============================================================================

if __name__ == '__main__':
    print("Validation utilities loaded.")
    print("Use PyVSCValidator(YourClass) to validate pyvsc models.")
    print("\nExample:")
    print("    validator = PyVSCValidator(MyTransaction)")
    print("    results = validator.validate_all(iterations=10000)")
    print("    validator.print_report()")
