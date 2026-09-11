#ifndef CARRIER_TEST_H
#define CARRIER_TEST_H
#include <stdint.h>
#include <stdlib.h>

/* Bench-only manual clutch A/B control.
 * A: (2404/3)*15*20/360=6010/9 count per carrier 20 degrees.
 * B: (2404/3)*12*20/360=4808/9 count per ring 20 degrees; direction is opposite.
 * The 70% fixed output matches the previously verified manual drive setting. */
#define CARRIER_MOVE_PWM_PERCENT 70
#define CARRIER_COUNT_TOLERANCE 3
#define CARRIER_SETTLE_MS 300U
#define CARRIER_MOVE_TIMEOUT_MS 10000U
#define CARRIER_STALL_MS 700U
#define CARRIER_LINK_TIMEOUT_MS 500U
#define CARRIER_MAX_ABS_STEPS 18
#define CARRIER_MAX_ABS_COUNT 12100
#define CARRIER_OBSERVATION_MODE 1 /* 1: coast after target crossing and record final error. */
#define MOTOR2_PWM_TO_COUNT_SIGN -1 /* Verified: positive PWM made PB3/PB5 count decrease. */
enum { CT_UNREFERENCED, CT_READY, CT_MOVING, CT_DONE, CT_FAULT };
enum { CE_NONE, CE_COMMAND, CE_LINK, CE_TIMEOUT, CE_STALL, CE_DIRECTION,
       CE_WHEEL_MOVED, CE_RANGE, CE_DRIFT };
enum { CLUTCH_NONE, CLUTCH_A, CLUTCH_B };
typedef struct {
  uint8_t state, error, referenced, target_reached, clutch_mode;
  char previous_command;
  int32_t zero_count, target_count, previous_count, previous_wheel, start_count;
  int32_t progress_count;
  uint32_t quiet_since, started_ms, progress_ms;
  int16_t angle_tenths, pwm_percent, target_step;
} CarrierTest;

static int CarrierTargetForStep(const CarrierTest *c, int32_t step, int32_t *target)
{
  if (step > CARRIER_MAX_ABS_STEPS || step < -CARRIER_MAX_ABS_STEPS) return 0;
  int64_t counts_numerator;
  if (c->clutch_mode == CLUTCH_A) counts_numerator = 6010;
  else if (c->clutch_mode == CLUTCH_B) counts_numerator = -4808;
  else return 0;
  int64_t numerator = (int64_t)step * counts_numerator;
  int64_t offset = numerator >= 0 ? (numerator + 4) / 9 : (numerator - 4) / 9;
  int64_t result = (int64_t)c->zero_count + offset;
  if (result > INT32_MAX || result < INT32_MIN) return 0;
  *target = (int32_t)result;
  return 1;
}

static void CarrierFault(CarrierTest *c, uint8_t error)
{
  c->state = CT_FAULT; c->error = error; c->referenced = 0; c->pwm_percent = 0;
}

/* Called every 10ms with one coherent input snapshot. No HAL dependencies. */
static void CarrierTick(CarrierTest *c, uint32_t now, int32_t count,
                        int32_t wheel, char cmd, uint32_t received_ms, int link_error)
{
  if (count != c->previous_count || wheel != c->previous_wheel) c->quiet_since = now;
  int wheel_changed = wheel != c->previous_wheel;
  c->previous_count = count; c->previous_wheel = wheel;
  c->pwm_percent = 0;
  if (link_error || now - received_ms > CARRIER_LINK_TIMEOUT_MS) {
    CarrierFault(c, CE_LINK); c->previous_command = 0; return;
  }
  if (cmd != 'a' && cmd != 'b' && cmd != 'z' && cmd != 'p' &&
      cmd != 'n' && cmd != 'r' && cmd != 'k' && cmd != 'h') {
    CarrierFault(c, CE_COMMAND); c->previous_command = cmd; return;
  }
  if (cmd != c->previous_command) {
    char previous = c->previous_command;
    c->previous_command = cmd;
    if (cmd == 'k') {
      if (c->state == CT_MOVING) c->referenced = 0;
      if (c->state != CT_FAULT) c->state = c->referenced ? CT_READY : CT_UNREFERENCED;
    } else if (cmd == 'h') {
      /* Heartbeat only: keep the current target and state. */
    } else if (cmd == 'a' || cmd == 'b') {
      if (c->state == CT_MOVING || previous != 'k' ||
          now - c->quiet_since < CARRIER_SETTLE_MS) {
        CarrierFault(c, CE_COMMAND); return;
      }
      c->clutch_mode = cmd == 'a' ? CLUTCH_A : CLUTCH_B;
      c->referenced = 0; c->target_reached = 0; c->target_step = 0;
      c->zero_count = count; c->target_count = count;
      c->state = CT_UNREFERENCED; c->error = CE_NONE;
    } else if (cmd == 'z') {
      if (c->state == CT_MOVING || c->clutch_mode == CLUTCH_NONE ||
          now - c->quiet_since < CARRIER_SETTLE_MS) {
        CarrierFault(c, CE_COMMAND); return;
      }
      c->zero_count = count; c->target_count = count; c->target_step = 0;
      c->target_reached = 0;
      c->referenced = 1; c->state = CT_READY; c->error = CE_NONE;
    } else {
      if (!c->referenced || c->state == CT_MOVING || now - c->quiet_since < CARRIER_SETTLE_MS) {
        CarrierFault(c, CE_COMMAND); return;
      }
      int32_t next_step = cmd == 'p' ? (int32_t)c->target_step + 1 :
                          cmd == 'n' ? (int32_t)c->target_step - 1 : 0;
      int32_t target;
      if (!CarrierTargetForStep(c, next_step, &target)) { CarrierFault(c, CE_RANGE); return; }
      c->target_step = (int16_t)next_step;
      c->target_count = target; c->start_count = count;
      c->target_reached = 0;
      c->started_ms = now; c->progress_ms = now; c->progress_count = count;
      c->quiet_since = now; c->state = CT_MOVING;
    }
  }
  if (c->referenced) {
    int64_t delta = (int64_t)count - c->zero_count;
    /* A: +180/601 tenths/count. B ring: -225/601 tenths/count. */
    if (delta > CARRIER_MAX_ABS_COUNT || delta < -CARRIER_MAX_ABS_COUNT) {
      CarrierFault(c, CE_RANGE); return;
    }
    c->angle_tenths = c->clutch_mode == CLUTCH_B
        ? (int16_t)(-delta * 225 / 601)
        : (int16_t)(delta * 180 / 601);
  } else c->angle_tenths = 0;
#if !CARRIER_OBSERVATION_MODE
  if (c->state == CT_DONE && llabs((int64_t)c->target_count - count) > CARRIER_COUNT_TOLERANCE) {
    CarrierFault(c, CE_DRIFT); return;
  }
#endif
  if (c->state != CT_MOVING) return;
  if (wheel_changed) { CarrierFault(c, CE_WHEEL_MOVED); return; }
  if (now - c->started_ms >= CARRIER_MOVE_TIMEOUT_MS) { CarrierFault(c, CE_TIMEOUT); return; }
  int64_t error = (int64_t)c->target_count - count;
  int direction = c->target_count >= c->start_count ? 1 : -1;
  if (((int64_t)count - c->start_count)*direction < -4) { CarrierFault(c, CE_DIRECTION); return; }
  if (c->target_reached) {
    if (now - c->quiet_since >= CARRIER_SETTLE_MS) c->state = CT_DONE;
    return;
  }
  int target_crossed = error * direction < 0;
#if CARRIER_OBSERVATION_MODE
  int reached_now = llabs(error) <= CARRIER_COUNT_TOLERANCE || target_crossed;
#else
  if (target_crossed) { CarrierFault(c, CE_RANGE); return; }
  int reached_now = llabs(error) <= CARRIER_COUNT_TOLERANCE;
#endif
  if (reached_now) {
    c->target_reached = 1;
    c->progress_ms = now; c->progress_count = count;
    if (now - c->quiet_since >= CARRIER_SETTLE_MS) c->state = CT_DONE;
    return;
  }
  if (llabs((int64_t)count - c->progress_count) >= 2) {
    c->progress_count = count; c->progress_ms = now;
  }
  if (now - c->progress_ms >= CARRIER_STALL_MS) { CarrierFault(c, CE_STALL); return; }
  c->pwm_percent = (int16_t)(direction * MOTOR2_PWM_TO_COUNT_SIGN *
                             CARRIER_MOVE_PWM_PERCENT);
}
#endif
