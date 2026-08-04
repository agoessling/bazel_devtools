class SwingState {
 public:
  static constexpr int kFrameRate = 240;

 protected:
  int timestamp_ns_;

 private:
  int frame_count_;
  static const int kSampleCount = 4;
};

struct SwingFrame {
  int frame_index;
  static constexpr int kFrameRate = 240;
};
