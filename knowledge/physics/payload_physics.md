# Payload Physics - Alpha CR10

## Current Default Configuration
- Camera: ARRI Alexa Mini (2.3 kg)
- Lens: Zeiss Master Prime 35mm (1.6 kg)
- FIZ System: Preston MDR4 (0.4 kg)
- Mount Hardware: ~0.5 kg
- **Total Payload: 4.8 kg**

## CR10 Payload Limits
- Maximum Payload: 10.0 kg
- Maximum CoM Offset: 50mm from J6 axis
- Current Configuration: Within limits (48% capacity)

## Center of Mass Analysis
- Combined CoM offset: X: +39.9mm, Y: +2.9mm, Z: +10.5mm
- Primary CoM contributor: Camera body (45mm X offset)
- CoM offset is approaching 50mm limit (warning threshold: 40mm)

## Joint Torque Analysis (Home Position)
| Joint | Rated Torque (Nm) | Load % | Status |
|-------|-------------------|--------|--------|
| J1    | 544               | 10.6%  | OK     |
| J2    | 544               | 10.6%  | OK     |
| J3    | 180               | 16.3%  | OK     |
| J4    | 55                | 11.5%  | OK     |
| J5    | 55                | 3.4%   | OK     |
| J6    | 28                | 6.7%   | OK     |

## Maximum Tested Configurations
- ARRI Alexa 35 + Zeiss MP 85mm + MDR4 + Matte Box: 7.5 kg (75% capacity)
- Sony Venice 2 + Cooke S4 50mm: 6.99 kg (70% capacity) - EXCEEDS CoM LIMIT
- RED V-Raptor + Zeiss MP 50mm + MDR4: 5.45 kg (55% capacity)

## Safety Notes
- Always verify payload with calculate_payload() before mounting
- Joint torques increase significantly at extended arm positions
- Worst case: J3 at 90 deg with full arm extension doubles torque on J2/J3
- Dynamic loads during rapid motion can exceed static torque estimates
- Never exceed 80% torque margin at any joint for sustained operation
