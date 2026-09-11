#include <assert.h>
#include <stdio.h>
#include "carrier_test.h"
static CarrierTest ready_mode(uint8_t clutch_mode) {
  CarrierTest c = {0};
  c.clutch_mode = clutch_mode;
  CarrierTick(&c, 0, -6, 0, 'k', 0, 0);
  CarrierTick(&c, 400, -6, 0, 'z', 400, 0);
  assert(c.state == CT_READY && c.zero_count == -6);
  return c;
}
static CarrierTest ready(void) { return ready_mode(CLUTCH_A); }
int main(void) {
  CarrierTest selected = {0};
  CarrierTick(&selected,0,-6,0,'k',0,0);
  CarrierTick(&selected,400,-6,0,'a',400,0);
  assert(selected.clutch_mode==CLUTCH_A && selected.state==CT_UNREFERENCED);
  CarrierTick(&selected,410,-6,0,'h',410,0);
  CarrierTick(&selected,420,-6,0,'z',420,0);
  assert(selected.state==CT_READY);
  CarrierTick(&selected,430,-6,0,'k',430,0);
  CarrierTick(&selected,740,-6,0,'b',740,0);
  assert(selected.clutch_mode==CLUTCH_B && !selected.referenced);

  CarrierTest c = ready();
  CarrierTick(&c,410,-6,0,'p',410,0);
  assert(c.state==CT_MOVING && c.target_count==662 && c.pwm_percent==-70);
  CarrierTick(&c,420,650,0,'p',420,0);
  assert(c.target_count==662 && c.pwm_percent==-70); /* repeated pulse is idempotent */
  CarrierTick(&c,425,655,0,'h',425,0);
  assert(c.target_count==662 && c.pwm_percent==-70); /* heartbeat retains target */
  CarrierTick(&c,430,662,0,'h',430,0);
  assert(c.state==CT_MOVING && c.pwm_percent==0);
  CarrierTick(&c,740,662,0,'h',740,0);
  assert(c.state==CT_DONE && c.angle_tenths==200);
  CarrierTick(&c,750,662,0,'p',750,0);
  assert(c.state==CT_MOVING && c.target_step==2 && c.target_count==1330 && c.pwm_percent==-70);
  CarrierTick(&c,760,700,0,'k',760,0);
  assert(c.state==CT_UNREFERENCED && !c.referenced && c.pwm_percent==0);
  c=ready(); CarrierTick(&c,410,-6,0,'p',410,0);
  CarrierTick(&c,420,662,0,'h',420,0);
  CarrierTick(&c,730,662,0,'h',730,0);
  CarrierTick(&c,740,662,0,'n',740,0);
  assert(c.state==CT_MOVING && c.target_step==0 && c.target_count==-6 && c.pwm_percent==70);
  c=ready(); CarrierTick(&c,410,-6,0,'n',410,0);
  assert(c.target_count==-674 && c.pwm_percent==70);
  c=ready_mode(CLUTCH_B); CarrierTick(&c,410,-6,0,'p',410,0);
  assert(c.target_count==-540 && c.pwm_percent==70);
  CarrierTick(&c,420,-540,0,'h',420,0);
  CarrierTick(&c,730,-540,0,'h',730,0);
  assert(c.state==CT_DONE && c.angle_tenths==199);
  CarrierTick(&c,740,-540,0,'n',740,0);
  assert(c.target_step==0 && c.target_count==-6 && c.pwm_percent==-70);
  c=ready(); CarrierTick(&c,410,-6,0,'p',410,0);
  CarrierTick(&c,420,-12,0,'p',420,0);
  assert(c.state==CT_FAULT && c.error==CE_DIRECTION && !c.referenced);
  c=ready(); CarrierTick(&c,410,-6,0,'p',410,0);
  CarrierTick(&c,1120,-6,0,'p',1120,0);
  assert(c.error==CE_STALL && c.pwm_percent==0);
  c=ready(); CarrierTick(&c,410,-6,0,'p',410,0);
  CarrierTick(&c,920,0,0,'p',410,0);
  assert(c.error==CE_LINK && c.pwm_percent==0);
  c=ready(); CarrierTick(&c,410,-6,0,'p',410,0);
  CarrierTick(&c,10410,100,0,'p',10410,0);
  assert(c.error==CE_TIMEOUT);
  c=ready(); CarrierTick(&c,410,-6,0,'p',410,0);
  CarrierTick(&c,420,0,1,'p',420,0);
  assert(c.error==CE_WHEEL_MOVED);
  c=ready(); CarrierTick(&c,410,-6,0,'p',410,0);
  CarrierTick(&c,420,670,0,'p',420,0);
  assert(c.state==CT_MOVING && c.target_reached && c.pwm_percent==0); /* overshoot: coast */
  CarrierTick(&c,500,710,0,'h',500,0);
  assert(c.state==CT_MOVING && c.error==CE_NONE && c.pwm_percent==0);
  CarrierTick(&c,810,710,0,'h',810,0);
  assert(c.state==CT_DONE && c.error==CE_NONE && c.angle_tenths==214);
  CarrierTick(&c,820,715,0,'h',820,0);
  assert(c.state==CT_DONE && c.error==CE_NONE); /* drift is recorded, not latched */
  CarrierTick(&c,1130,715,0,'n',1130,0);
  assert(c.state==CT_MOVING && c.target_step==0 && c.target_count==-6 && c.pwm_percent==70);
  c=ready(); CarrierTick(&c,410,-6,0,'u',410,0);
  assert(c.error==CE_COMMAND && c.pwm_percent==0);
  CarrierTick(&c,420,-6,0,'k',420,0);
  CarrierTick(&c,430,-6,0,'z',430,0);
  assert(c.state==CT_READY);
  c=(CarrierTest){0}; CarrierTick(&c,400,0,0,'p',400,0);
  assert(c.state==CT_FAULT); /* no reference */
  c=ready(); CarrierTick(&c,410,-6,0,'p',410,0);
  CarrierTick(&c,420,-6,0,'n',420,0);
  assert(c.error==CE_COMMAND); /* no retargeting during motion */
  c=ready(); c.zero_count=INT32_MAX;
  CarrierTick(&c,410,-6,0,'p',410,0);
  assert(c.error==CE_RANGE);
  c=ready(); c.target_step=CARRIER_MAX_ABS_STEPS;
  CarrierTick(&c,410,-6,0,'p',410,0);
  assert(c.error==CE_RANGE && c.pwm_percent==0);
  c=ready(); CarrierTick(&c,410,-6,0,'p',410,1);
  assert(c.error==CE_LINK);
  puts("carrier controller: all assertions passed");
  return 0;
}
