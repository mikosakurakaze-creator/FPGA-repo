#include "fixed_math.hpp"
#include <iostream>
int main() {
    int checks=0;
    const auto check=[&](bool ok) { ++checks; if(!ok) throw std::runtime_error("fixed math check"); };
    for(int s=1;s<=20;++s) {
        const auto half=std::int64_t(1)<<(s-1);
        check(gdn::round_shift(half,s)==1);
        check(gdn::round_shift(-half,s)==-1);
        check(gdn::round_shift(half-1,s)==0);
        check(gdn::round_shift(-half+1,s)==0);
        check(gdn::round_shift(3*half,s)==2);
        check(gdn::round_shift(-3*half,s)==-2);
    }
    check(gdn::round_shift(INT64_MIN,1)==INT64_MIN/2);
    check(gdn::round_shift(INT64_MAX,1)==INT64_MAX/2+1);
    check(gdn::round_shift(-32768,-14)==-536870912);
    check(gdn::round_shift(32767,-14)==536854528);
    check(gdn::sat(-32769)==-32768); check(gdn::sat(32768)==32767);
    check(gdn::sat(-32768)==-32768); check(gdn::sat(32767)==32767);
    bool rejected=false;
    try { (void)gdn::round_shift(INT64_MAX,-1); } catch(const std::overflow_error&) { rejected=true; }
    check(rejected);
    // Branches must align wide before add, without premature INT16 saturation.
    check(gdn::sat(gdn::round_shift(20000,-1)+gdn::round_shift(-15000,-1))==10000);
    std::cout<<"B_FIXED_MATH_PASS checks="<<checks<<"\n";
}
